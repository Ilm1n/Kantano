import { createApp, createSSRApp } from "vue";
import LandingPage from "./pages/LandingPage.vue";
import { bootstrapAnalytics } from "@/shared/analytics/bootstrap";
import "@/shared/ui/styles";

const root = document.getElementById("app")!;
const app = import.meta.env.DEV
  ? createApp(LandingPage)
  : createSSRApp(LandingPage);
app.mount(root);
bootstrapAnalytics();
