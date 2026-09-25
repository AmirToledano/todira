import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import Contact from "./Contact.jsx";

const mount = document.getElementById("root");
if (mount) {
  createRoot(mount).render(
    <StrictMode>
      <Contact />
    </StrictMode>,
  );
}
