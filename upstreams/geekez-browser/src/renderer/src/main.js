import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'

const app = createApp(App)

app.config.globalProperties.$t = (key) => {
    return window.t ? window.t(key) : key;
};

app.use(createPinia())
app.mount('#app')
