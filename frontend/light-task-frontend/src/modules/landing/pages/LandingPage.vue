<script setup lang="ts">
import { ref} from 'vue';
import { useRouter } from 'vue-router';
import { useTheme } from '@/composables/useTheme';
import { useWindowScroll } from '@vueuse/core';
import { openCookieSettings } from '@/shared/consent/consent';

import avatar1 from '@/assets/images/testimonials/user1.webp';
import avatar2 from '@/assets/images/testimonials/user2.webp';
import avatar3 from '@/assets/images/testimonials/user3.webp';
// UI Components
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import Accordion from 'primevue/accordion';
import AccordionPanel from 'primevue/accordionpanel';
import AccordionHeader from 'primevue/accordionheader';
import AccordionContent from 'primevue/accordioncontent';
import Drawer from 'primevue/drawer';
import Card from 'primevue/card';
import Tabs from 'primevue/tabs';
import TabList from 'primevue/tablist';
import Tab from 'primevue/tab';
import TabPanels from 'primevue/tabpanels';
import TabPanel from 'primevue/tabpanel';

const router = useRouter();
const { isDark, toggleTheme } = useTheme();
const { y } = useWindowScroll();

const email = ref('');
const isMobileMenuOpen = ref(false);

const navigateToRegister = () => {
  router.push({ name: 'register', query: { email: email.value } });
};

const scrollToTop = () => {
  window.scrollTo({ top: 0, behavior: 'smooth' });
};


const workflows = [
  {
    id: 'dev',
    title: 'Разработка',
    desc: 'Управляйте спринтами, отслеживайте баги и делайте релизы вовремя.',
    items: ['Backlog', 'In Progress', 'Code Review', 'Done']
  },
  {
    id: 'design',
    title: 'Дизайн',
    desc: 'Визуализируйте процесс создания интерфейсов от идеи до финального макета.',
    items: ['Research', 'Wireframes', 'UI Design', 'Feedback']
  },
  {
    id: 'marketing',
    title: 'Маркетинг',
    desc: 'Планируйте кампании и контент-план в удобном интерфейсе.',
    items: ['Ideas', 'Writing', 'Graphic', 'Published']
  }
];

const reviews = [
  { name: 'Алексей Иванов', role: 'Project Manager', text: 'Kantano заменил нам тяжеловесную Jira. Скорость работы просто поражает.', avatar: avatar1 },
  { name: 'Мария Петрова', role: 'Frontend Developer', text: 'Лучший интерфейс для канбан-досок. Все интуитивно и очень красиво.', avatar: avatar2 },
  { name: 'Дмитрий Соколов', role: 'Startup Founder', text: 'Мы запустили MVP на 2 недели раньше благодаря планированию в Kantano.', avatar: avatar3 }
];

const plans = [
  { name: 'Free', price: '0', features: ['До 3 проектов', 'Канбан-доски', 'До 5 участников'], current: false },
  { name: 'Pro', price: '490', features: ['Безлимит проектов', 'Умные теги', 'Приоритетная поддержка'], current: true },
  { name: 'Team', price: '1200', features: ['Все из Pro', 'Админ-панель', 'API доступ'], current: false }
];

const faqList = [
  {
    q: "Какие ограничения у бесплатной версии?",
    a: "Бесплатный тариф 'Free' навсегда останется бесплатным. Он включает создание до 3 проектов и командную работу до 5 человек. Этого достаточно для стартапов, студентов и личного планирования."
  },
  {
    q: "Нужно ли обновлять страницу, чтобы увидеть изменения?",
    a: "Нет. Kantano использует технологию WebSockets для мгновенной синхронизации. Если ваш коллега передвинет задачу или изменит описание, вы увидите это в ту же секунду без перезагрузки."
  },
  {
    q: "Работает ли Kantano на телефоне?",
    a: "Да, интерфейс полностью адаптирован для мобильных устройств. Вы можете управлять задачами через браузер или добавить сайт на главный экран как приложение (PWA)."
  },
  {
    q: "Насколько безопасны мои данные?",
    a: "Мы используем современные стандарты шифрования (SSL) и защищенные протоколы авторизации (JWT). Ваши проекты доступны только тем участникам, которых вы лично пригласили."
  },
  {
    q: "Как быстро пригласить команду?",
    a: "Очень просто. Зайдите в настройки проекта, сгенерируйте пригласительную ссылку (или QR-код) и отправьте коллегам в мессенджер. Им останется только зарегистрироваться."
  }
];
</script>

<template>
  <div class="landing-root bg-white dark:bg-dark-bg text-slate-900 dark:text-slate-100 transition-colors duration-300 scroll-smooth">

    <Transition name="fade">
      <button v-show="y > 400" @click="scrollToTop" class="fixed bottom-8 right-8 z-[110] w-12 h-12 rounded-full bg-primary-600 text-white shadow-2xl flex items-center justify-center hover:scale-110 active:scale-90 transition-all">
        <i class="pi pi-arrow-up"></i>
      </button>
    </Transition>

    <!-- HEADER -->
    <header role="banner" class="sticky top-0 z-[100] bg-white/90 dark:bg-dark-bg/90 backdrop-blur-md border-b border-slate-200 dark:border-dark-border">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        <div class="flex items-center gap-8">
          <router-link to="/" class="flex items-center gap-2 no-underline">
            <i class="pi pi-bolt text-primary-600 text-2xl"></i>
            <span class="text-xl font-extrabold tracking-tighter uppercase">Kantano</span>
          </router-link>
          <nav class="hidden lg:flex items-center gap-6">
            <a href="#why" class="nav-link">Преимущества</a>
            <a href="#workflows" class="nav-link">Решения</a>
            <a href="#pricing" class="nav-link">Цены</a>
            <a href="#faq" class="nav-link">FAQ</a>
          </nav>
        </div>
        <div class="flex items-center gap-3">
          <button @click="toggleTheme" class="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors" aria-label="Сменить тему">
            <i :class="isDark ? 'pi pi-sun' : 'pi pi-moon'"></i>
          </button>
          <div class="hidden sm:flex items-center gap-3">
            <router-link to="/login" class="font-bold text-slate-600 dark:text-slate-400 hover:text-primary-600 px-4 no-underline">Войти</router-link>
            <Button label="Начать" class="!bg-primary-600 dark:!text-white !border-none !font-bold !px-6" @click="router.push('/register')" />
          </div>
          <button @click="isMobileMenuOpen = true" aria-label="Открыть меню" class="lg:hidden p-2 text-slate-600 dark:text-slate-400"><i class="pi pi-bars text-xl"></i></button>
        </div>
      </div>
    </header>

    <!-- MOBILE MENU  -->
    <Drawer
        v-model:visible="isMobileMenuOpen"
        position="right"
        header="Меню"
        class="!w-72 !bg-white dark:!bg-dark-bg dark:!text-slate-100 !border-none"
    >
      <div class="flex flex-col gap-4 mt-4">
        <a href="#why" @click="isMobileMenuOpen = false" class="mobile-nav-link">Преимущества</a>
        <a href="#workflows" @click="isMobileMenuOpen = false" class="mobile-nav-link">Решения</a>
        <a href="#pricing" @click="isMobileMenuOpen = false" class="mobile-nav-link">Цены</a>
        <a href="#faq" @click="isMobileMenuOpen = false" class="mobile-nav-link">FAQ</a>
        <hr class="border-slate-100 dark:border-slate-800" />
        <Button label="Войти" outlined class="dark:!text-white w-full !bg-primary-600/5 !text-primary-600  !border-primary-600" @click="router.push('/login')" />
        <Button label="Регистрация" class="dark:!text-white w-full !bg-primary-600 !border-none" @click="router.push('/register')" />
      </div>
    </Drawer>

    <main>
      <!-- HERO SECTION -->
      <section class="hero-gradient pt-20 pb-24 px-4 overflow-hidden">
        <div class="max-w-7xl mx-auto grid lg:grid-cols-2 gap-12 items-center text-center lg:text-left">
          <div class="text-left z-10">
            <h1 class="text-4xl sm:text-6xl font-black leading-[1.05] mb-6 tracking-tight">
              Kantano объединяет <br/>
              <span class="text-primary-600">команды и задачи</span>
            </h1>
            <p class="text-xl text-slate-600 dark:text-slate-400 mb-10 max-w-lg leading-relaxed">
              Управляйте проектами, достигайте новых высот и работайте в своем ритме — от малого бизнеса до крупных команд.
            </p>

            <form @submit.prevent="navigateToRegister" class="flex flex-col sm:flex-row gap-3 max-w-md">
              <InputText v-model="email" placeholder="Email" class="flex-1 !py-3 !px-4 !text-lg !rounded-xl" aria-label="Ваш email для регистрации" />
              <Button type="submit" label="Регистрация" class="!bg-primary-600 dark:!text-white  !border-none !py-3 !px-6 !font-bold !rounded-xl" />
            </form>
            <p class="mt-4 text-sm text-slate-400">Присоединяйтесь к 1,000+ пользователям сегодня.</p>
          </div>
          <div class="relative lg:block hidden animate-float">
            <div class="bg-slate-100 dark:bg-slate-800 rounded-3xl p-6 shadow-2xl border border-slate-200 dark:border-slate-700">
              <div class="flex gap-4 mb-6">
                <div class="w-1/3 h-4 bg-slate-300 dark:bg-slate-600 rounded"></div>
                <div class="w-1/3 h-4 bg-slate-200 dark:bg-slate-700 rounded"></div>
              </div>
              <div class="grid grid-cols-2 gap-4">
                <div class="p-4 bg-white dark:bg-slate-900 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-700">
                  <div class="h-2 w-full bg-primary-100 dark:bg-primary-900/40 rounded mb-2"></div>
                  <div class="h-2 w-2/3 bg-slate-100 dark:bg-slate-800 rounded"></div>
                </div>
                <div class="p-4 bg-primary-600 rounded-2xl shadow-lg text-white">
                  <div class="h-2 w-full bg-white/30 rounded mb-2"></div>
                  <div class="h-2 w-1/2 bg-white/20 rounded"></div>
                </div>
              </div>
              <div class="grid grid-cols-2 gap-4 mt-5">
                <div class="p-4 bg-white dark:bg-slate-900 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-700">
                  <div class="h-2 w-full bg-primary-100 dark:bg-primary-900/40 rounded mb-2"></div>
                  <div class="h-2 w-2/3 bg-slate-100 dark:bg-slate-800 rounded"></div>
                </div>
                <div class="p-4 bg-primary-600 rounded-2xl shadow-lg text-white">
                  <div class="h-2 w-full bg-white/30 rounded mb-2"></div>
                  <div class="h-2 w-1/2 bg-white/20 rounded"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- LOGOS -->
      <section class="py-12 border-y border-slate-200 dark:border-dark-border opacity-80 grayscale hover:grayscale-0 transition-all duration-700">
        <h2 class="text-center  text-2xl font-black mb-16">
          Нам доверяют лучшие команды
        </h2>
        <div class="max-w-7xl mx-auto px-4 flex flex-wrap justify-center gap-12 md:gap-24 items-center">
          <span class="text-2xl font-bold tracking-widest text-slate-400">ЯНДЕКС</span>
          <span class="text-2xl font-bold tracking-widest text-slate-400">SELECTEL</span>
          <span class="text-2xl font-bold tracking-widest text-slate-400">AVITO</span>
          <span class="text-2xl font-bold tracking-widest text-slate-400">OZON</span>
        </div>
      </section>

      <!-- Why Kantano? -->
      <section id="why" class="py-24 px-4">
        <div class="max-w-7xl mx-auto">
          <div class="text-center mb-16">
            <h2 class="text-4xl font-black mb-4">Почему выбирают нас?</h2>
            <p class="text-slate-500 max-w-2xl mx-auto">Мы фокусируемся на том, что действительно важно для продуктивной работы.</p>
          </div>
          <div class="grid md:grid-cols-3 gap-12">
            <div class="text-center group">
              <div class="w-16 h-16 bg-blue-100 dark:bg-blue-900/30 text-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-6 group-hover:scale-110 transition-transform">
                <i class="pi pi-bolt text-2xl"></i>
              </div>
              <h3 class="text-xl font-bold mb-3">Мгновенный отклик</h3>
              <p class="text-slate-500 text-sm leading-relaxed dark:!text-slate-300">Никаких лишних загрузок. Легкий интерфейс обеспечивает плавность работы уровня нативного приложения.</p>
            </div>
            <div class="text-center group">
              <div class="w-16 h-16 bg-purple-100 dark:bg-purple-900/30 text-purple-600 rounded-2xl flex items-center justify-center mx-auto mb-6 group-hover:scale-110 transition-transform">
                <i class="pi pi-lock text-2xl"></i>
              </div>
              <h3 class="text-xl font-bold mb-3">Безопасность данных</h3>
              <p class="text-slate-500 text-sm leading-relaxed dark:!text-slate-300">Ваши данные зашифрованы и принадлежат только вам. Мы используем современные стандарты JWT.</p>
            </div>
            <div class="text-center group">
              <div class="w-16 h-16 bg-green-100 dark:bg-green-900/30 text-green-600 rounded-2xl flex items-center justify-center mx-auto mb-6 group-hover:scale-110 transition-transform">
                <i class="pi pi-users text-2xl"></i>
              </div>
              <h3 class="text-xl font-bold mb-3">Командный дух</h3>
              <p class="text-slate-500 text-sm leading-relaxed dark:!text-slate-300">Удобная система ролей и приглашений. Работайте вместе так, будто вы сидите в одном офисе.</p>
            </div>
          </div>
        </div>
      </section>

      <!-- WORKFLOWS SECTION  -->
      <section id="workflows" class="py-24 px-4 bg-slate-50 dark:bg-slate-900/20">
        <div class="max-w-5xl mx-auto">
          <div class="text-center mb-16">
            <h2 class="text-4xl font-black mb-4">Решение для <span class="text-primary-600">любой задачи</span></h2>
            <p class="text-slate-500">Kantano подойдет под любой вид работы</p>
          </div>

          <Tabs value="dev">
            <TabList class="flex justify-center mb-12 !border-none !bg-transparent">
              <Tab v-for="w in workflows" :key="w.id" :value="w.id" class="!px-8 !py-3 !font-bold dark:text-slate-400">
                {{ w.title }}
              </Tab>
            </TabList>
            <TabPanels class="!bg-transparent">
              <TabPanel v-for="w in workflows" :key="w.id" :value="w.id">
                <div class="grid md:grid-cols-2 gap-12 items-center bg-white dark:bg-slate-800 p-8 md:p-12 rounded-[3rem] shadow-xl border border-slate-100 dark:border-slate-700">
                  <div>
                    <h3 class="text-3xl font-black mb-6 dark:text-slate-300">{{ w.title }}</h3>
                    <p class="text-slate-500 dark:text-slate-300 mb-8 text-lg leading-relaxed">{{ w.desc }}</p>

                  </div>
                  <div class="bg-slate-50 dark:bg-slate-900 p-6 rounded-2xl border border-slate-100 dark:border-slate-700">
                    <div class="flex flex-col gap-3">
                      <div v-for="(item, idx) in w.items" :key="idx"
                           class="p-4 bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-100 dark:border-slate-700 flex items-center justify-between"
                           :style="{ opacity: 1 - idx * 0.15 }">
                        <span class="font-bold text-sm dark:text-slate-300">{{ item }}</span>
                        <i class="pi pi-ellipsis-v text-slate-300"></i>
                      </div>
                    </div>
                  </div>
                </div>
              </TabPanel>
            </TabPanels>
          </Tabs>
        </div>
      </section>

      <!-- TESTIMONIALS -->
      <section class="py-24 px-4">
        <div class="max-w-7xl mx-auto">
          <h2 class="text-center text-4xl font-black mb-16">О нас говорят</h2>
          <div class="grid md:grid-cols-3 gap-8">
            <Card v-for="review in reviews" :key="review.name" class="!rounded-3xl dark:!bg-slate-800 border dark:!border-slate-700 !border-slate-100 shadow-sm">
              <template #content>
                <p class="italic text-slate-600 dark:text-slate-400 mb-6">"{{ review.text }}"</p>
                <div class="flex items-center gap-4">
                  <img :src="review.avatar" loading="lazy" width="48" height="48" class="w-12 h-12 rounded-full" :alt="`Фото пользователя ${review.name}`"  />
                  <div>
                    <p class="font-bold text-sm dark:text-slate-300">{{ review.name }}</p>
                    <p class="text-xs text-slate-500 dark:text-slate-300">{{ review.role }}</p>
                  </div>
                </div>
              </template>
            </Card>
          </div>
        </div>
      </section>

      <!-- PRICING (FIXED BUTTONS) -->
      <section id="pricing" class="py-24 px-4 bg-slate-50 dark:bg-slate-900/20">
        <div class="max-w-7xl mx-auto">
          <div class="text-center mb-16">
            <h2 class="text-4xl font-black mb-4">Простые тарифы</h2>
            <p class="text-slate-500 dark:!text-slate-300">Выберите план для вашей команды</p>
          </div>
          <div class="grid md:grid-cols-3 gap-8 items-center ">
            <div v-for="plan in plans" :key="plan.name"
                 class="p-8 rounded-[2.5rem] border transition-all duration-300"
                 :class="plan.current ? ' bg-white dark:bg-slate-900 border-primary-500 shadow-2xl scale-105 z-10' : 'border-slate-200 dark:border-dark-border bg-transparent opacity-80'">
              <h3 class="text-xl font-bold mb-4 ">{{ plan.name }}</h3>
              <div class="text-4xl font-black mb-6 ">{{ plan.price }}₽ <span class="text-sm  dark:!text-slate-300 font-normal text-slate-500">/мес</span></div>
              <ul class="space-y-4 mb-8">
                <li v-for="f in plan.features" :key="f" class="flex items-center gap-3 text-sm">
                  <i class="pi pi-check text-primary-500 "></i> {{ f }}
                </li>
              </ul>
              <Button
                  :label="plan.name === 'Free' ? 'Начать бесплатно' : 'Выбрать'"
                  class="w-full !rounded-2xl !py-3 transition-all"
                  :class="plan.current
                  ? '!bg-primary-600 !border-none !text-white'
                  : '!text-slate-700 dark:!text-slate-200 !border-slate-300 dark:!border-slate-600 !bg-transparent hover:!bg-slate-100 dark:hover:!bg-slate-800'"
                  :outlined="!plan.current"
                  @click="router.push('/register')"
              />
            </div>
          </div>
        </div>
      </section>

      <!-- FAQ -->
      <section id="faq" class="py-24 px-4 max-w-3xl mx-auto">
        <h2 class="text-center text-3xl sm:text-4xl font-black mb-12 text-slate-800 dark:text-white">
          Часто задаваемые вопросы
        </h2>

        <Accordion :value="['0']" multiple>
          <AccordionPanel v-for="(item, index) in faqList" :key="index" :value="String(index)">
            <AccordionHeader class="!text-slate-700 dark:!text-slate-300 !font-bold">
              {{ item.q }}
            </AccordionHeader>
            <AccordionContent>
              <p class="text-slate-500 dark:text-slate-400 leading-relaxed text-sm sm:text-base">
                {{ item.a }}
              </p>
            </AccordionContent>
          </AccordionPanel>
        </Accordion>
      </section>

      <!-- FINAL CTA -->
      <section class="py-24 px-4">
        <div class="max-w-5xl mx-auto
                    bg-primary-600 dark:bg-slate-800/40
                    rounded-[3rem] p-12 md:p-20 text-center text-white
                    shadow-2xl relative overflow-hidden
                    border border-transparent dark:border-primary-500/20 backdrop-blur-sm">


          <div class="absolute top-0 right-0 w-64 h-64 bg-white/10 dark:bg-primary-500/10 blur-3xl rounded-full -mr-32 -mt-32"></div>
          <div class="absolute bottom-0 left-0 w-64 h-64 bg-black/10 dark:bg-blue-500/10 blur-3xl rounded-full -ml-32 -mb-32"></div>

          <h2 class="text-4xl md:text-6xl font-black mb-8 relative z-10 tracking-tight">
            Готовы навести порядок <br/>
            <span class="text-white dark:text-primary-400">в своих задачах?</span>
          </h2>

          <p class="text-white/80 dark:text-slate-300 text-xl mb-12 max-w-2xl mx-auto relative z-10 leading-relaxed">
            Присоединяйтесь к пользователям, которые уже выбрали Kantano для управления своими проектами.
          </p>

          <div class="flex flex-col sm:flex-row justify-center gap-4 relative z-10">
            <Button
                label="Зарегистрироваться"
                class="!py-4 !px-10 !text-lg !font-bold !rounded-2xl shadow-xl transition-transform hover:scale-105 active:scale-95
                     !bg-white !text-primary-600 !border-none
                     dark:!bg-primary-600 dark:!text-white dark:!border-none"
                @click="router.push('/register')"
            />



          </div>
        </div>
      </section>
    </main>

    <!-- FOOTER -->
    <footer class="bg-slate-900 text-white pt-20 pb-10 px-4" role="contentinfo">
      <div class="max-w-7xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-12 mb-16">
        <div class="col-span-2 md:col-span-1">
          <div class="flex items-center gap-2 mb-6"><i class="pi pi-bolt text-primary-500 text-2xl"></i><span class="text-xl font-black uppercase tracking-tighter">Kantano</span></div>
          <p class="text-slate-400 text-sm">Сделано с любовью к коду.</p>
        </div>
        <div>
          <h3 class="font-bold mb-6">Продукт</h3>
          <nav class="flex flex-col gap-4 text-slate-400 text-sm">
            <a href="#why" class="hover:text-white transition-colors no-underline">Преимущества</a>
            <a href="#workflows" class="hover:text-white transition-colors no-underline">Решения</a>
            <a href="#pricing" class="hover:text-white transition-colors no-underline">Цены</a>
            <a href="#faq" class="hover:text-white transition-colors no-underline">FAQ</a>
          </nav>
        </div>
        <div>
          <h3 class="font-bold mb-6">Ресурсы</h3>
          <nav class="flex flex-col gap-4 text-slate-400 text-sm">
            <a href="https://github.com/Ilm1n" target="_blank" rel="noopener noreferrer" class="hover:text-white transition-colors no-underline">GitHub</a>
            <button
              type="button"
              class="text-left hover:text-white transition-colors"
              @click="openCookieSettings"
            >
              Настройки cookie
            </button>
          </nav>
        </div>
        <div>
          <h3 class="font-bold mb-6">Связь</h3>
          <nav class="flex flex-col gap-4 text-slate-400 text-sm">
            <a href="https://t.me/Ilm1n" target="_blank" rel="noopener noreferrer"  class="hover:text-white transition-colors no-underline">Telegram</a>
            <a href="mailto:mininiv2005@gmail.com" class="hover:text-white transition-colors no-underline">Email</a>
            <a href="tel:+79219826283" class="hover:text-white transition-colors no-underline">+7 (921) 982-62-83</a>
          </nav>
        </div>
      </div>
      <div class="max-w-7xl mx-auto pt-8 border-t border-slate-800 text-center text-slate-500 text-xs">
        <p>© 2026 Kantano.</p>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

.nav-link { @apply text-sm font-bold text-slate-600 dark:text-slate-400 hover:text-primary-600 transition-colors no-underline; }
.mobile-nav-link { @apply text-xl font-bold py-2 no-underline text-slate-800 dark:text-slate-100; }
.hero-gradient { background: radial-gradient(circle at 70% 30%, rgba(59, 130, 246, 0.08) 0%, transparent 50%), radial-gradient(circle at 10% 80%, rgba(139, 92, 246, 0.05) 0%, transparent 40%); }
@keyframes float { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-20px); } }
.animate-float { animation: float 6s ease-in-out infinite; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

:deep(.p-tablist-tab-list) {
  @apply !border-none !bg-slate-100/50 dark:!bg-slate-800/50 !p-1 !rounded-2xl;
}
:deep(.p-tab) {
  @apply !border-none !rounded-xl !transition-all;
}
:deep(.p-tab-active) {
  @apply !bg-white dark:!bg-slate-700 !shadow-sm !text-primary-600;
}

:deep(.p-accordionheader) { @apply !bg-transparent !border-none !py-6 !font-bold !text-lg; }
:deep(.p-accordioncontent-content) { @apply !bg-transparent !border-none !pt-0 !pb-6; }

:deep(.p-drawer-header) {
  @apply dark:!bg-dark-bg dark:!text-slate-100;
}

:deep(.p-accordionheader) {
  @apply !bg-transparent !border-none !py-6 !font-bold !text-lg;
  outline: none !important;
  transition: background-color 0.2s, color 0.2s, box-shadow 0.2s !important;
}

:deep(.p-accordionheader:focus-visible) {
  box-shadow: 0 0 0 2px var(--p-primary-500) !important;
}
</style>
