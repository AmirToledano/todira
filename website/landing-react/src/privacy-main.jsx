import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import Privacy from "./Privacy.jsx";

const mount = document.getElementById("root");
if (mount) {
  createRoot(mount).render(
    <StrictMode>
      <Privacy />
    </StrictMode>,
  );
}
