import React from "react";
import ReactDOM from "react-dom/client";
import { Toaster } from "sonner";
import App from "./App.jsx";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <div className="min-h-screen">
      <App />
      <Toaster position="top-right" richColors theme="dark" />
    </div>
  </React.StrictMode>
);
