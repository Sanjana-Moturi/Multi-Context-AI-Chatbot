import React, { useState, useEffect, useRef } from "react";
import { IoMdSend } from "react-icons/io";
import axios from "axios"
import { useLocation } from "react-router-dom";

function Chat() {
    const location =useLocation();

    const [messages, setMessages] = useState([]);
    const [userQuery, setUserQuery] = useState("");
    const [loading, setLoading] = useState(false);
    const messagesEndRef = useRef(null);
    const {username}=location.state;


    const sendMessage = async () => {
        if (!userQuery.trim()) return;
        const currentMessage = userQuery;
        setMessages((prev) => [
            ...prev, {
                user: currentMessage,
                bot: ""
            }
        ]);
        setUserQuery("");
        setLoading(true);
        try {
            const res = await axios.post("http://127.0.0.1:8000/chat", { user_query: currentMessage, username:"username" });
            setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1].bot = res.data.response;
                return updated;
            });
        } catch (err) {
            console.log(err);
        }
        finally {
            setLoading(false);
        }

    };
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, loading]);

    return (
        <div>
            <div className="behind">
                <div className="display">
                    <div className="chatting">
                        {messages.map((msg, index) => (
                            <div key={index}>
                                <div className="user-container">
                                    <p className="user-msg">
                                        {msg.user}
                                    </p>
                                </div>

                                <div className="bot-container">
                                    <p className="bot-msg">
                                        {msg.bot}
                                    </p>
                                </div>
                            </div>
                        ))
                        }
                        {loading && (
                            <p>AI is typing...</p>
                        )}
                        <div ref={messagesEndRef}></div>
                    </div>
                    <div className="chat-bar">
                        <input type="text" placeholder="Enter your query" value={userQuery} onChange={(e) => setUserQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { sendMessage(); } }} />
                        <div className="icon" onClick={sendMessage}>
                            <IoMdSend />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default Chat;