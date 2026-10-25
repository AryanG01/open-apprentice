import { createRoot } from "react-dom/client";
import { App } from "./App";
import "@fontsource/barlow/400.css";
import "@fontsource/barlow/500.css";
import "@fontsource/barlow/600.css";
import "@fontsource/barlow-semi-condensed/600.css";
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import "./styles.css";

createRoot(document.getElementById("root")!).render(<App />);
