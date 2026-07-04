from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_groq import ChatGroq
from sentence_transformers import util
import torch
from database.db import db, cursor
import config
from prompts.system_prompts import SYSTEM_PROMPT
import mysql.connector
import ast
import re
import json
import requests

app = FastAPI(
    title="chatbot",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

embeddings = HuggingFaceEmbeddings(
    model_name=config.EMBEDDING_MODEL,
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

vectorstore = FAISS.load_local(
    "faiss_index",
    embeddings,
    allow_dangerous_deserialization=True,
)

retriever = vectorstore.as_retriever(
    search_kwargs={"k": config.TOP_K}
)

llm = ChatGroq(
    groq_api_key=config.GROQ_API_KEY,
    model_name=config.GROQ_MODEL
)
def search_docs(query):
    if len(query.strip()) < 3:
        return []
    docs = retriever.invoke(query)
    return docs

class ChatResponse(BaseModel):
    user_query: str
    username: str

class LoginRequest(BaseModel):
    username: str


def split_queries(user_query):
    prompt = f"""
    Split the user query into meaningful independent questions.

    Rules:
    - Keep dependent parts together
    - Split ONLY fully independent requests
    - Do NOT split references like:
        - their
        - those
        - it
        - them
        - related details
    - Return ONLY python list

    Example 1:
    Input:
    holidays in april and their locations? also give my email

    Output:
    [
      "holidays in april and their locations",
      "give my email"
    ]

    Example 2:
     Input:
    give my email and sanj password

    Output:
    [
      "give my email",
      "sanj password"
    ]

    User Query:
    {user_query}
    """

    response = llm.invoke(prompt)

    try:
        queries = ast.literal_eval(response.content)
        return queries
    except:
        return [user_query]


def get_schema():
    schema_cursor = db.cursor()
    schema_cursor.execute(""" SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, COLUMN_KEY FROM information_schema.columns WHERE TABLE_SCHEMA='ajaydemo' AND TABLE_NAME NOT IN ('chats','knowledge')""")
    rows = schema_cursor.fetchall()
    schema_text = ""
    tables = {}
    for row in rows:
        table_name = row[0]
        col_name = row[1]
        col_type = row[2]
        col_key = row[3]

        if table_name not in tables:
            tables[table_name] = []

        tables[table_name].append( f"{col_name} ({col_type}) KEY:{col_key}")

    for table, cols in tables.items():
        schema_text += f"\nTable: {table}\n"
        schema_text += "Columns:\n"
        for col in cols:
            schema_text += f"- {col}\n"

    schema_cursor.execute(""" SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA='ajaydemo' AND REFERENCED_TABLE_NAME IS NOT NULL""")
    relations = schema_cursor.fetchall()
    schema_text += "\nRelationships:\n"
    if relations:
        for rel in relations:
            schema_text += (
                f"- {rel[0]}.{rel[1]} "
                f"-> {rel[2]}.{rel[3]}\n"
            )
    else:
        schema_text += "- No foreign key relationships defined\n"

    schema_cursor.close()
    return schema_text

schema = get_schema()

def detect_unauthorized(user_query, username):
    blocked_messages = []
    sensitive_words = [
        "otp",
        "password",
        "pin",
        "cvv",
        "passcode"
    ]

    for word in sensitive_words:
        if word in user_query.lower():
            blocked_messages.append(
                "Sensitive information cannot be shared."
            )
            break

    temp_cursor = db.cursor()
    temp_cursor.execute("SELECT username FROM users")
    users = temp_cursor.fetchall()
    temp_cursor.close()
    for row in users:
        db_username = row[0]
        if ( db_username.lower() in user_query.lower() and db_username.lower() != username.lower()):
            blocked_messages.append( f"Personal information of {db_username} cannot be shared.")

    return blocked_messages


def generate_sql(schema_text, user_query, username):
    prompt = f"""
    You are an expert MySQL query generator.

    Database Schema:
    {schema_text}

    Logged In Username:
    {username}

    Rules:
    - Return ONLY SQL query
    - Do not explain
    - Use MySQL syntax
    - Use proper table names
    - Never generate DELETE, DROP, UPDATE, TRUNCATE
    - Only generate SELECT queries
    - Strictly consider table relations properly using Database Schema
    - Never expose OTPs or passwords
    - NEVER assume relationships
    - Use ONLY relationships explicitly defined
    - If no relationship exists never JOIN tables
    - Do not infer joins from similar column names
    - If query is unrelated to database tables return: NO_SQL

    Security Rules:
    - Generate SQL ONLY for valid requests
    - Ignore unauthorized requests
    - Logged-in user can access ONLY their own details
    - Never generate SQL for:
        - other users personal information
        - otp/password/pin/cvv/passcode
    - Apply username filtering ONLY for personal tables like:
        users,
        profile,
        accounts,
        employee,
        customer
    - Do NOT add USERID filters for public/general tables
    - General tables for example like holidays, states, cities are public

    User Question:
    {user_query}
    """
    response = llm.invoke(prompt)
    sql_query = response.content.strip()
    sql_query = sql_query.replace("```sql", "")
    sql_query = sql_query.replace("```", "")
    sql_query = sql_query.strip()

    if sql_query.upper()=="NO_SQL":
        return None
    return sql_query


def execute_sql(sql_query):
    try:
        blocked_words = [
            "DELETE",
            "DROP",
            "TRUNCATE",
            "UPDATE",
            "INSERT",
            "ALTER"
        ]
        upper_query = sql_query.upper()
        for word in blocked_words:
            if word in upper_query:
                return {
                    "blocked": True,
                    "response": "Invalid query."
                }

        sensitive_words = [
            "OTP",
            "PIN",
            "PASSWORD",
            "CVV",
            "PASSCODE"
        ]

        for word in sensitive_words:
            if word in upper_query:
                return {
                    "blocked": True,
                    "response": "Sensitive information cannot be shared."
                }

        if not sql_query.strip():
            return {
                "blocked": False,
                "rows": []
            }

        temp_cursor = db.cursor(dictionary=True)
        temp_cursor.execute(sql_query)
        rows = temp_cursor.fetchall()
        while temp_cursor.nextset():
            pass
        columns = temp_cursor.column_names
        temp_cursor.close()
        return {
            "blocked": False,
            "rows": rows,
            "columns": columns
        }

    except Exception as e:
        print("SQL ERROR:", e)
        return {
            "blocked": True,
            "response": "Database error."
        }

cursor.execute("SELECT content FROM knowledge")
rows = cursor.fetchall()
texts = [r[0] for r in rows]
db_embeddings = embeddings.embed_documents(texts)

def get_knowledge_context(user_query):
    if not texts:
        return ""
    query_embedding = embeddings.embed_query(user_query)
    similarities = util.cos_sim(
        torch.tensor(query_embedding),
        torch.tensor(db_embeddings)
    )[0]
    matched = []
    for idx, score in enumerate(similarities):
        if score.item() > 0.28:
            matched.append(texts[idx])

    return "\n".join(matched)


API_ENDPOINTS = [
    {
        "name": "states",
        "endpoint": "http://192.168.1.162:8080/demo/api/state",
        "description": """
        Contains all states information.
        state name,mapped country state-(country code,country name,status),its status
        Can answer:
        - state details
        - country it is mapped to
        - state status
        """
    },
    {
        "name": "countries",
        "endpoint": "http://192.168.1.162:8080/demo/api/countries",
        "description": """
        Contains countries information.
        country name,country code and its status
        Can answer:
        - country details
        - nations
        - world countries
        """
    },{
        "name": "cities",
        "endpoint": "http://192.168.1.162:8080/demo/api/city",
        "description": """
        Contains all cities information.
        city name,mapping country city,mapping state city,its status
        Can answer:
        - city details
        - country it is mapped to
        - city status
        - state it is mapped to
        """
    },
    {
        "name": "state_id",
        "endpoint": "http://127.0.0.1:5000/api/state/{id}",
        "placeholders": {
        "id": "numeric state id"
        },
        "description": """
        Contains states information by id.
        state name,mapped country state-(country code,country name,status),its status
        Can answer:
        - state details
        - country it is mapped to
        - state status
        """
    }
]

def detect_relevant_apis(user_query):
    api_text = ""
    for api in API_ENDPOINTS:
        api_text += f"""
        API NAME:
        {api['name']}

        ENDPOINT:
        {api['endpoint']}

        DESCRIPTION:
        {api['description']}
        """

    prompt = f"""
    You are an intelligent API router.

    Your task:
    Detect which APIs are required for answering the user query.

    ==================================================
    AVAILABLE APIs:
    {api_text}
    ==================================================

    RULES:
    - Return ONLY valid python list
    - Do NOT explain
    - Match SEMANTICALLY
    - Do NOT depend only on exact keywords
    - Multiple APIs can be selected
    - If no API needed return []

    IMPORTANT:
    - Keep endpoint placeholders EXACTLY as given
    - NEVER replace placeholders
    - NEVER modify endpoint strings

    ==================================================

    Examples:

    User Query:
    what is the status of tamilnadu

    Output:
    [
        "http://192.168.1.162:8080/demo/api/state"
    ]

    --------------------------------------------------

    User Query:
    tell me about kerala

    Output:
    [
        "http://192.168.1.162:8080/demo/api/state"
    ]

    --------------------------------------------------

    User Query:
    list all countries

    Output:
    [
        "http://192.168.1.162:8080/demo/api/countries"
    ]

    --------------------------------------------------

    User Query:
    give state 3 details

    Output:
    [
        "http://127.0.0.1:5000/api/state/{id}"
    ]

    --------------------------------------------------

    User Query:
    holidays in april

    Output:
    []

    ==================================================

    USER QUERY:
    {user_query}
    """

    response = llm.invoke(prompt)

    try:
        api_list = ast.literal_eval(
            response.content
        )
        return api_list

    except Exception as e:
        print("API ROUTER ERROR:", e)
        return []

def extract_placeholders(api_url):
    return re.findall(r"\{(.*?)\}",api_url)

def extract_dynamic_values(user_query, placeholders):
    prompt = f"""
    Extract values for placeholders from user query.
    Return ONLY valid JSON.
    PLACEHOLDERS:
    {placeholders}

    Example:

    Placeholders:
    ["state"]

    User Query:
    what is the status of tamilnadu

    Output:
    {{
        "state": "tamilnadu"
    }}

    -----------------------------------

    Placeholders:
    ["country"]

    User Query:
    tell me about india

    Output:
    {{
        "country": "india"
    }}


    -----------------------------------

    Placeholders:
    ["id"]

    User Query:
    state id 5 details

    Output:
    {{
        "id": "5"
    }}
    -----------------------------------

    Placeholders:
    ["username", "id"]

    User Query:
    get user san with id 5

    Output:
    {{
        "username": "san",
        "id": "5"
    }}

    -----------------------------------

    USER QUERY:
    {user_query}
    """

    response = llm.invoke(prompt)

    try:
        return json.loads(response.content)

    except:
        return {}
    
def build_api_url(api_url, user_query, logged_username):
    placeholders =  extract_placeholders(api_url)
    values = extract_dynamic_values(user_query, placeholders)

    values["username"] = logged_username
    final_url = api_url
    for placeholder in placeholders:
        value = values.get(placeholder, "")
        final_url = final_url.replace(
            "{" + placeholder + "}",
            str(value)
        )
    return final_url


def get_api_context(user_query, username):
    api_context = ""
    matched_apis = detect_relevant_apis( user_query)
    print("Matched APIs:", matched_apis)
    allowed_urls = [
        api["endpoint"]
        for api in API_ENDPOINTS
    ]

    for raw_api in matched_apis:
        if raw_api not in allowed_urls:
            continue
        try:
            final_api = build_api_url( raw_api, user_query, username)
            response = requests.get( final_api, timeout=5)

            if response.status_code == 200:
                data = response.json()
                api_context += ( f"API URL:\n{final_api}\n\n")

                api_context += (
                    f"API RESPONSE:\n"
                    f"{json.dumps(data, indent=2)}\n\n"
                )

        except Exception as e:
            print("API ERROR:", e)

    return api_context

def is_smalltalk(text):
    text = text.strip().lower()
    smalltalk = {
        "ok",
        "okay",
        "hi",
        "hello",
        "thanks",
        "thank you",
        "hmm",
        "yes",
        "no",
        "fine",
        "cool",
        "great",
        "nice",
        "okiee",
        "alright",
        "bye",
        "nope"
    }
    return text in smalltalk

@app.post("/login")
def login(data: LoginRequest):
    username = data.username
    temp_cursor = db.cursor(dictionary=True)
    query = "SELECT * FROM users WHERE BINARY username=%s"
    values = (username,)
    temp_cursor.execute(query, values)
    user = temp_cursor.fetchone()
    temp_cursor.close()
    if not user:
        return {
            "success": False,
            "message": "User not found"
        }

    return {
        "success": True,
        "message": "Login successful"
    }

@app.post("/chat")
def save_chat(data: ChatResponse):
    user_query = data.user_query
    if is_smalltalk(user_query):
        bot_response="okayy"
        temp_cursor = db.cursor()
        query = """
        INSERT INTO chats(user_query, bot_response) VALUES (%s, %s)
        """
        temp_cursor.execute(query, (user_query, bot_response))
        db.commit()
        temp_cursor.close()
        return{
            "message":"success",
            "response":"okayy"
        }
    username = "sanj"
    docs = search_docs(user_query)
    pdf_context_global = "\n".join([doc.page_content for doc in docs]) if docs else ""
    queries = split_queries(user_query)

    final_answers = []
    for q in queries:
        knowledge_context = get_knowledge_context(q)
        api_context=""
        sql=None
        warnings = detect_unauthorized(q, username)
        if warnings:
            final_answers.extend(warnings)
            continue
        if not knowledge_context.strip():
            api_context=get_api_context(q, username)
        
        if not api_context.strip() and not knowledge_context.strip():
            sql = generate_sql(schema, q, username)
        db_context = ""
        if sql:
            print("Generated SQL:")
            print(sql)

            result = execute_sql(sql)
        
            if result and not result.get("blocked") and "rows" in result:
                rows = result["rows"]
                if rows:
                    for row in rows:
                        for key, value in row.items():
                            db_context += f"{key}: {value}\n"
                        db_context += "\n"

        merged_context = ""
        if db_context.strip():
            merged_context += f"DATABASE CONTEXT:\n{db_context}\n\n"

        if knowledge_context.strip():
            merged_context += f"KNOWLEDGE CONTEXT:\n{knowledge_context}\n\n"

        if api_context.strip():
            merged_context += f"API CONTEXT:\n{api_context}\n\n"

        if pdf_context_global.strip():
            merged_context += f"PDF CONTEXT:\n{pdf_context_global}\n\n"


        if merged_context.strip():
            answer_prompt = f"""
                {SYSTEM_PROMPT}

                User Question:
                {q}

                Context:
                {merged_context}

                Answer naturally using the best available information.
                """

            answer = llm.invoke(answer_prompt).content
            final_answers.append(answer)
            continue


        general_answer = llm.invoke(q).content
        final_answers.append(general_answer)

    bot_response = "\n\n".join(final_answers)

    temp_cursor = db.cursor()
    query = """
    INSERT INTO chats(user_query, bot_response) VALUES (%s, %s)
    """

    temp_cursor.execute(query, (user_query, bot_response))
    db.commit()
    temp_cursor.close()
    return {
        "message": "Saved Successfully",
        "response": bot_response
    }