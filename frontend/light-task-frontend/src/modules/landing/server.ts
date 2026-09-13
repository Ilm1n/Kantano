import { createSSRApp } from "vue";
import { renderToString } from "vue/server-renderer";
import LandingPage from "./pages/LandingPage.vue";

export function render(): Promise<string> {
  return renderToString(createSSRApp(LandingPage));
}
