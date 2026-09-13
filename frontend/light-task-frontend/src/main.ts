import {createApp} from 'vue';
import {createPinia} from 'pinia';
import { createHead } from '@unhead/vue/client';
import App from './App.vue';
import router from './router';
import PrimeVue from 'primevue/config';
import { KantanoPreset } from '@/shared/ui/primevue';
import ToastService from 'primevue/toastservice';
import ConfirmationService from 'primevue/confirmationservice';


import '@/shared/ui/styles';
import { bootstrapAnalytics } from '@/shared/analytics/bootstrap';

const app = createApp(App);
const head = createHead();

app.use(createPinia());
app.use(router);
app.use(head);
bootstrapAnalytics(router);

app.use(PrimeVue, {
  theme: {
    preset: KantanoPreset,
    options: {
      darkModeSelector: '.dark',
    }
  }
});
app.use(ToastService);
app.use(ConfirmationService);

app.mount('#app');
