import { onMounted, ref } from "vue";

const isDark = ref(false);

export function useTheme() {
  onMounted(() => {
    isDark.value = document.documentElement.classList.contains("dark");
  });
  const toggleTheme = () => {
    isDark.value = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", isDark.value);
    localStorage.setItem("theme", isDark.value ? "dark" : "light");
  };
  return { isDark, toggleTheme };
}
