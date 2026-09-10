import { createApp } from 'vue'
import App from './App.vue'

// Vuetify e Iconos
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

const vuetify = createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'light',
    themes: {
      light: {
        colors: {
          primary: '#059669',
          secondary: '#F1F5F9',
          accent: '#059669',
          background: '#F8FAFC',
          surface: '#FFFFFF',
          error: '#B91C1C',
          warning: '#B45309',
          info: '#0369A1',
          success: '#059669'
        }
      }
    }
  }
})

const app = createApp(App)
app.use(vuetify)
app.mount('#app')
