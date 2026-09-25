import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import Terms from "./Terms.jsx";

const mount = document.getElementById("root");
if (mount) {
  createRoot(mount).render(
    <StrictMode>
      <Terms />
    </StrictMode>,
  );
}
