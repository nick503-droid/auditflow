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
          primary: '#0F172A', // Slate 900 (Dark elegant)
          secondary: '#3B82F6', // Blue 500
          accent: '#10B981', // Emerald 500 (Success)
          background: '#F1F5F9', // Slate 100
          surface: '#FFFFFF',
          error: '#EF4444', // Red 500
        }
      }
    }
  }
})

const app = createApp(App)
app.use(vuetify)
app.mount('#app')
