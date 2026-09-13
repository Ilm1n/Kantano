<script setup lang="ts">
import {
  getCurrentInstance,
  onMounted,
  onUnmounted,
  ref,
  shallowRef,
  type Component,
} from "vue";
import { useTheme } from "@/composables/useTheme";
import { openCookieSettings } from "@/shared/consent/consent";
import avatar1 from "@/assets/images/testimonials/user1.webp";
import avatar2 from "@/assets/images/testimonials/user2.webp";
import avatar3 from "@/assets/images/testimonials/user3.webp";
const { toggleTheme } = useTheme();
const ready = ref(false);
const showBackToTop = ref(false);
const updateScroll = () => {
  showBackToTop.value = window.scrollY > 400;
};
const scrollToTop = () => {
  window.scrollTo({
    top: 0,
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "instant"
      : "smooth",
  });
};
const closeMobileMenu = (event: MouseEvent) => {
  const target = event.target as HTMLElement;
  if (target.closest("a")) target.closest("details")?.removeAttribute("open");
};
const cookieControls = shallowRef<Component>();
const app = getCurrentInstance()!.appContext.app;
onMounted(async () => {
  ready.value = true;
  updateScroll();
  window.addEventListener("scroll", updateScroll, { passive: true });
  const [{ default: PrimeVue }, { KantanoPreset }, { default: controls }] =
    await Promise.all([
      import("primevue/config"),
      import("@/shared/ui/primevue"),
      import("@/shared/ui/CookieBanner.vue"),
    ]);
  app.use(PrimeVue, {
    theme: { preset: KantanoPreset, options: { darkModeSelector: ".dark" } },
  });
  cookieControls.value = controls;
});
onUnmounted(() => {
  window.removeEventListener("scroll", updateScroll);
});
const scenarios = [
  [
    "Личный проект",
    "Поездка, ремонт или своя идея: разложите большой план на небольшие задачи и двигайтесь в своём темпе.",
  ],
  [
    "Учёба",
    "Соберите задания и сроки по курсовой на одной доске. Материалы, черновик и подготовка к защите — каждый этап на виду.",
  ],
  [
    "Фриланс",
    "Отделяйте новые задачи от работы, которая уже началась, и того, что ждёт проверки заказчика.",
  ],
  [
    "Учебная группа",
    "Распределите части презентации, назначьте ответственных и следите за общим прогрессом без пересылки списков.",
  ],
];
const reviews = [
  {
    name: "Алексей Иванов",
    role: "Project Manager",
    text: "Kantano заменил нам тяжеловесную Jira. Скорость работы просто поражает.",
    avatar: avatar1,
  },
  {
    name: "Мария Петрова",
    role: "Frontend Developer",
    text: "Лучший интерфейс для канбан-досок. Все интуитивно и очень красиво.",
    avatar: avatar2,
  },
  {
    name: "Дмитрий Соколов",
    role: "Startup Founder",
    text: "Мы запустили MVP на 2 недели раньше благодаря планированию в Kantano.",
    avatar: avatar3,
  },
];
const faqs = [
  [
    "Можно пользоваться одному?",
    "Да. Создайте проект для своих дел, добавьте задачи и назовите колонки так, как удобно вам. Приглашать других участников необязательно.",
  ],
  [
    "Подойдёт для учебной группы?",
    "Да. На общей доске можно распределить задачи между участниками и указать сроки. Изменения появляются без перезагрузки страницы.",
  ],
  [
    "Что доступно бесплатно?",
    "Проекты, канбан-доски, задачи, свои колонки, сроки, приоритеты, теги, фильтры и совместная работа доступны бесплатно.",
  ],
  [
    "Можно уже подключить Plus?",
    "Пока нет: Plus находится в разработке. Возможности и стоимость сообщим позже. Сейчас можно пользоваться бесплатной версией.",
  ],
  [
    "Как пригласить участников?",
    "Откройте проект, нажмите «Пригласить» и создайте ссылку или QR-код. Отправьте приглашение тем, с кем работаете над проектом.",
  ],
  [
    "Можно работать с телефона?",
    "Да, Kantano открывается в браузере на телефоне. Для работы нужно подключение к интернету.",
  ],
];
const features = [
  {
    title: "У каждой задачи — свой этап",
    text: "Создайте свои колонки и перемещайте карточки по мере работы. Видно, что ещё предстоит сделать, что уже в процессе и что готово.",
    image: "columns",
    width: 320,
    height: 599,
    alt: "Задачи на разных этапах доски",
  },
  {
    title: "Важное легче найти",
    text: "Отмечайте сроки и приоритеты, добавляйте теги. Фильтры помогут сосредоточиться на нужных задачах, когда доска станет больше.",
    image: "filters",
    width: 381,
    height: 416,
    alt: "Фильтры задач по исполнителю, тегам и приоритету",
  },
  {
    title: "Вместе — на одной доске",
    text: "Приглашайте участников по ссылке или QR-коду и назначайте исполнителей. Изменения появляются без перезагрузки — каждый видит актуальный план.",
    image: "invite",
    width: 396,
    height: 462,
    alt: "Приглашение участников в проект Kantano",
  },
];
</script>

<template>
  <div class="landing">
    <a href="#main" class="skip-link">К содержанию</a>
    <header class="site-header">
      <div class="wrap header-inner">
        <a class="brand" href="/" aria-label="Kantano — главная"
          ><i class="pi pi-bolt" aria-hidden="true"></i>Kantano</a
        >
        <nav class="desktop-nav" aria-label="Основная навигация">
          <a href="#features">Возможности</a><a href="#scenarios">Сценарии</a
          ><a href="#pricing">Тарифы</a><a href="#faq">FAQ</a>
        </nav>
        <div class="header-actions">
          <button
            v-if="ready"
            class="theme-button"
            aria-label="Сменить тему"
            @click="toggleTheme"
          >
            <i class="pi pi-moon light-icon" aria-hidden="true"></i
            ><i class="pi pi-sun dark-icon" aria-hidden="true"></i>
          </button>
          <a href="/login">Войти</a
          ><a class="button header-cta" href="/register">Начать бесплатно</a>
          <details class="mobile-menu">
            <summary>Меню</summary>
            <nav aria-label="Мобильная навигация" @click="closeMobileMenu">
              <a href="#features">Возможности</a
              ><a href="#scenarios">Сценарии</a
              ><a href="#pricing">Тарифы</a><a href="#faq">FAQ</a
              ><a href="/register">Начать бесплатно</a>
            </nav>
          </details>
        </div>
      </div>
    </header>
    <main id="main">
      <section class="wrap hero" aria-labelledby="hero-title">
        <div class="hero-copy">
          <p class="eyebrow">Канбан-доска для повседневных дел</p>
          <h1 id="hero-title">Свои задачи —<br />в понятном порядке</h1>
          <p class="intro">
            Kantano — бесплатная канбан-доска для личных дел, учёбы и фриланса.
            Раскладывайте задачи по этапам, отмечайте сроки и работайте над
            общими проектами вместе.
          </p>
          <div class="hero-actions">
            <a class="button" href="/register">Начать бесплатно</a
            ><a class="text-link" href="#features"
              >Посмотреть возможности <span aria-hidden="true">↓</span></a
            >
          </div>
        </div>
        <figure class="board-preview">
          <picture
            ><source
              media="(max-width: 640px)"
              srcset="/landing-board-mobile.webp"
              width="678"
              height="606" />
            <img
              src="/landing-board.webp"
              width="1460"
              height="704"
              fetchpriority="high"
              alt="Учебный проект в Kantano: задачи с тегами, сроками, приоритетами и исполнителями на разных этапах работы"
          /></picture>
          <figcaption>
            Так может выглядеть ваша доска. На примере учебного проекта.
          </figcaption>
        </figure>
      </section>
      <section
        id="features"
        class="section wrap"
        aria-labelledby="features-title"
      >
        <p class="eyebrow">Без сложной настройки</p>
        <h2 id="features-title">Понятно, что делать дальше</h2>
        <div
          v-for="feature in features"
          :key="feature.image"
          class="feature-row"
        >
          <div>
            <h3>{{ feature.title }}</h3>
            <p>{{ feature.text }}</p>
          </div>
          <img
            :src="`/landing-${feature.image}.webp`"
            :width="feature.width"
            :height="feature.height"
            loading="lazy"
            :alt="feature.alt"
          />
        </div>
      </section>
      <section
        id="scenarios"
        class="section section-muted"
        aria-labelledby="scenarios-title"
      >
        <div class="wrap">
          <h2 id="scenarios-title">Для своих дел и общих проектов</h2>
          <div class="scenarios">
            <article v-for="[title, text] in scenarios" :key="title">
              <h3>{{ title }}</h3>
              <p>{{ text }}</p>
            </article>
          </div>
        </div>
      </section>
      <section class="section wrap" aria-labelledby="reviews-title">
        <h2 id="reviews-title">О нас говорят</h2>
        <div class="reviews">
          <figure v-for="review in reviews" :key="review.name">
            <blockquote>{{ review.text }}</blockquote>
            <figcaption>
              <img
                :src="review.avatar"
                width="40"
                height="40"
                loading="lazy"
                :alt="review.name"
              />
              <div>
                <strong>{{ review.name }}</strong
                ><span>{{ review.role }}</span>
              </div>
            </figcaption>
          </figure>
        </div>
      </section>
      <section
        id="pricing"
        class="section wrap"
        aria-labelledby="pricing-title"
      >
        <h2 id="pricing-title">Тарифы</h2>
        <p class="pricing-intro">Начните бесплатно. Plus пока в разработке.</p>
        <div class="plans">
          <article class="free-plan">
            <h3>Бесплатно</h3>
            <p class="plan-price">0 ₽</p>
            <p>Всё, чтобы начать и вести свои проекты.</p>
            <ul>
              <li>Канбан-доски, задачи и свои колонки</li>
              <li>Сроки, приоритеты, теги и фильтры</li>
              <li>Приглашения и совместная работа</li>
            </ul>
            <a class="button" href="/register">Начать бесплатно</a>
          </article>
          <article class="future-plan">
            <h3>Plus <span class="status">В разработке</span></h3>
            <p>
              Готовим дополнительные возможности для тех, кто регулярно
              пользуется Kantano. Подробности и стоимость появятся позже.
            </p>
          </article>
        </div>
      </section>
      <section id="faq" class="section wrap faq" aria-labelledby="faq-title">
        <h2 id="faq-title">Вопросы перед началом</h2>
        <details v-for="[question, answer] in faqs" :key="question">
          <summary>{{ question }}</summary>
          <p>{{ answer }}</p>
        </details>
      </section>
      <section class="wrap final-cta">
        <h2>Соберите свои задачи<br />в одном месте</h2>
        <a class="button" href="/register">Начать бесплатно</a>
      </section>
    </main>
    <footer class="site-footer">
      <div class="wrap footer-grid">
        <div>
          <a class="brand" href="/">Kantano</a>
          <p>Задачи, которыми удобно заниматься.</p>
          <small>© 2026 Kantano</small>
        </div>
        <nav aria-label="Продукт">
          <a href="#features">Возможности</a><a href="#scenarios">Сценарии</a
          ><a href="#pricing">Тарифы</a><a href="#faq">Вопросы</a>
        </nav>
        <nav aria-label="Контакты">
          <a href="https://t.me/Ilm1n" target="_blank" rel="noopener noreferrer"
            >Telegram</a
          ><a href="mailto:mininiv2005@gmail.com">Email</a
          ><a href="tel:+79219826283">+7 (921) 982-62-83</a
          ><a
            href="https://github.com/Ilm1n"
            target="_blank"
            rel="noopener noreferrer"
            >GitHub</a
          ><button v-if="cookieControls" @click="openCookieSettings">
            Настройки cookie
          </button>
        </nav>
      </div>
    </footer>
    <button
      v-if="showBackToTop"
      class="back-to-top"
      aria-label="Вернуться наверх"
      @click="scrollToTop"
    >
      <i class="pi pi-arrow-up" aria-hidden="true"></i>
    </button>
    <component :is="cookieControls" v-if="cookieControls" />
  </div>
</template>

<style scoped src="../landing.css"></style>
