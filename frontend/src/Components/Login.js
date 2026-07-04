import React from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import axios from "axios";

function Login(){
    const [username,setUsername]=useState("");
    const navigate = useNavigate();

    const handleLogin=async()=>{
        if(!username.trim()){
            toast.error("Enter Username");
            return;
        }
        try {
            const res = await axios.post("http://127.0.0.1:8000/login", { username });
            if (res.data.success) {
                toast.success(`${username} Login successful!`);
                navigate("/chat", { state: { username: username } });
            } else {
                toast.error(res.data.message);
            }
            setUsername("");
        }
        catch (error) {
            console.log(error);
            toast.error("Server error");
        }
    }

    return(
        <div className="login">
            <div className="login-box">
                <h2>Login</h2>
                <input type="text" placeholder="Enter Username" onChange={(e)=>setUsername(e.target.value)} onKeyDown={(e)=>{if(e.key==='Enter')handleLogin();}}/>
                <button onClick={()=>{handleLogin()}}>Enter</button>
            </div>
        </div>
    )
}
export default Login;