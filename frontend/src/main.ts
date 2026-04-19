import { createApp } from 'vue'
import App from './App.vue'

console.log(
  '%cGenreGrid%c\nStyle-based MIDI generator\n%cCreated by TW Dover',
  'color:#00c8ff;font-size:22px;font-weight:700;letter-spacing:0.05em',
  'color:#4a7080;font-size:12px',
  'color:#2a6070;font-size:11px',
)

createApp(App).mount('#app')
