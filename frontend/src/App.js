import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import {Toaster} from "react-hot-toast";
import Chat from "./Components/Chat";
import "./Styles/ui.css";
import Login from "./Components/Login";
function App() {
  return (
    <BrowserRouter>
      <Toaster position="top-right" />
      <Routes>
          <Route path="/" element={<Login />} />
          <Route path="/chat" element={<Chat />} />
      </Routes>
  
    </BrowserRouter>
    
  );
}

export default App;
