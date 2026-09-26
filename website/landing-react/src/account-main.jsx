import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import Account from "./Account.jsx";

const mount = document.getElementById("root");
if (mount) {
  createRoot(mount).render(
    <StrictMode>
      <Account />
    </StrictMode>,
  );
}
