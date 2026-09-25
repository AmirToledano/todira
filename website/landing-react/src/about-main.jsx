import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import About from "./About.jsx";

const mount = document.getElementById("root");
if (mount) {
  createRoot(mount).render(
    <StrictMode>
      <About />
    </StrictMode>,
  );
}
