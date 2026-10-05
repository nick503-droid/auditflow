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
          primary: '#047857',
          // Mantiene el azul secundario del tema de escritorio y evita
          // controles outlined casi blancos sobre superficies claras.
          secondary: '#0369A1',
          accent: '#047857',
          background: '#F8FAFC',
          surface: '#FFFFFF',
          error: '#B91C1C',
          warning: '#B45309',
          info: '#0369A1',
          success: '#047857'
        }
      }
    }
  }
})

const app = createApp(App)
app.use(vuetify)
app.mount('#app')
