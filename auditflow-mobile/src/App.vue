<template>
  <v-app>
    <v-main class="app-background">
      <v-container class="fill-height d-flex flex-column justify-center align-center px-4 position-relative">
        
        <!-- Botón de Configuración -->
        <v-btn
          icon="mdi-cog"
          variant="text"
          color="white"
          class="position-absolute"
          style="top: 16px; right: 16px; z-index: 10;"
          @click="mostrarConfig = true"
        ></v-btn>

        <!-- Botón de Debugging (Logs) -->
        <v-btn
          icon="mdi-bug"
          variant="flat"
          color="warning"
          class="position-absolute rounded-circle elevation-4"
          style="bottom: 16px; left: 16px; z-index: 10;"
          @click="mostrarLogs = true"
        ></v-btn>

        <!-- Diálogo de Logs de Android -->
        <v-dialog v-model="mostrarLogs" fullscreen transition="dialog-bottom-transition">
          <v-card color="#0F172A" class="text-white">
            <v-toolbar color="warning">
              <v-btn icon="mdi-close" @click="mostrarLogs = false"></v-btn>
              <v-toolbar-title class="font-weight-bold">Consola Android</v-toolbar-title>
              <v-spacer></v-spacer>
              <v-btn icon="mdi-delete" @click="logs = []"></v-btn>
            </v-toolbar>
            <v-card-text class="pa-4 bg-black" style="font-family: monospace; overflow-y: auto; height: 100%;">
              <div v-for="(log, idx) in logs" :key="idx" class="mb-2 pb-2 border-b border-opacity-25" :class="log.type === 'error' ? 'text-red-lighten-1' : 'text-green-lighten-2'">
                <span class="font-weight-bold">[{{ log.type.toUpperCase() }}]</span> {{ log.msg }}
              </div>
              <div v-if="logs.length === 0" class="text-grey">No hay registros aún...</div>
            </v-card-text>
          </v-card>
        </v-dialog>

        <!-- Diálogo de Configuración -->
        <v-dialog v-model="mostrarConfig" max-width="400">
          <v-card color="#1E293B" class="text-white rounded-xl">
            <v-card-title class="pt-6 px-6 font-weight-bold">Configuración de Red</v-card-title>
            <v-card-text class="px-6">
              <p class="text-body-2 mb-4 text-grey-lighten-1">Si la IP del servidor cambia, ingrésala aquí para reconectar la app.</p>
              <v-text-field
                v-model="configUrl"
                label="URL del Servidor (Backend)"
                variant="outlined"
                color="primary"
                hide-details
                placeholder="Ej: http://192.168.1.29:3000"
              ></v-text-field>
            </v-card-text>
            <v-card-actions class="pb-6 px-6 pt-0">
              <v-spacer></v-spacer>
              <v-btn color="grey" variant="text" @click="mostrarConfig = false">Cancelar</v-btn>
              <v-btn color="primary" variant="flat" @click="guardarConfig">Guardar</v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

        <!-- Tarjeta Principal (Glassmorphism Effect) -->
        <v-card class="glass-card pa-8 rounded-xl w-100" max-width="450" elevation="0">
          <div class="text-center mb-8 fade-in-up">
            <div class="logo-container mx-auto mb-4">
              <v-icon icon="mdi-camera-iris" size="48" color="white"></v-icon>
            </div>
            <h1 class="text-h4 font-weight-black text-primary" style="letter-spacing: -1px;">AuditFlow</h1>
            <p class="text-subtitle-1 text-grey-darken-1 font-weight-medium mt-1">Sincronización de Evidencias</p>
          </div>

          <!-- PASO 1: Búsqueda de Destino -->
          <v-fade-transition hide-on-leave>
            <div v-if="paso === 1" class="w-100 fade-in-up delay-1">
              <div class="text-center mb-6">
                <span class="text-overline font-weight-bold text-primary">CÓDIGO DE VINCULACIÓN</span>
              </div>

              <!-- Input OTP 6 dígitos -->
              <v-otp-input
                v-model="codigo"
                length="6"
                type="text"
                class="mb-8 custom-otp"
                variant="solo-filled"
                bg-color="white"
                :disabled="subiendo"
                style="text-transform: uppercase;"
              ></v-otp-input>

              <v-btn
                color="primary"
                size="x-large"
                block
                class="text-none font-weight-bold gradient-btn"
                elevation="4"
                rounded="pill"
                @click="buscarDestino"
                :disabled="codigo.length !== 6 || subiendo"
                height="56"
              >
                <v-icon left class="mr-2" size="24">mdi-magnify</v-icon>
                Buscar Destino
              </v-btn>
            </div>
          </v-fade-transition>

          <!-- PASO 2: Confirmación y Captura -->
          <v-fade-transition hide-on-leave>
            <div v-if="paso === 2" class="w-100 fade-in-up">
              <!-- Resumen de Información (Premium Info Card) -->
              <v-card variant="flat" color="background" class="info-card mb-6 pa-5 rounded-xl border">
                <div class="d-flex align-center mb-4">
                  <v-avatar :color="infoDestino.tipo === 'bitacora' ? 'secondary' : 'warning'" size="48" class="mr-3 shadow-sm">
                    <v-icon color="white" size="24">
                      {{ infoDestino.tipo === 'bitacora' ? 'mdi-clipboard-text-clock' : 'mdi-alert-circle' }}
                    </v-icon>
                  </v-avatar>
                  <div>
                    <div class="text-overline font-weight-black text-grey-darken-2" style="line-height: 1.2;">DESTINO ENCONTRADO</div>
                    <div class="text-h6 font-weight-bold text-primary" style="line-height: 1.2;">
                      {{ infoDestino.tipo === 'bitacora' ? 'Bitácora Activa' : 'Reporte Activo' }}
                    </div>
                  </div>
                </div>

                <v-divider class="mb-4 border-opacity-50"></v-divider>

                <div class="info-grid">
                  <template v-if="infoDestino.tipo === 'bitacora'">
                    <div class="info-item">
                      <v-icon size="18" color="primary" class="mr-2">mdi-store</v-icon>
                      <span class="text-body-2 text-grey-darken-3 font-weight-medium">{{ infoDestino.restaurante }}</span>
                    </div>
                    <div class="info-item">
                      <v-icon size="18" color="primary" class="mr-2">mdi-clock-outline</v-icon>
                      <span class="text-body-2 text-grey-darken-3">{{ infoDestino.fecha }} &bull; {{ infoDestino.hora }}</span>
                    </div>
                    <div class="info-item">
                      <v-icon size="18" color="primary" class="mr-2">mdi-account-tie</v-icon>
                      <span class="text-body-2 text-grey-darken-3">{{ infoDestino.usuario }}</span>
                    </div>
                    <div class="info-item mt-2 info-desc pl-7 border-s-lg border-primary">
                      <span class="text-caption text-grey-darken-1">{{ infoDestino.descripcion }}</span>
                    </div>
                  </template>
                  <template v-else>
                    <div class="info-item">
                      <v-icon size="18" color="primary" class="mr-2">mdi-text-box</v-icon>
                      <span class="text-body-1 text-grey-darken-3 font-weight-bold">{{ infoDestino.titulo }}</span>
                    </div>
                  </template>
                </div>
                
                <div class="d-flex align-center mt-5 pt-3 border-t">
                  <v-icon color="accent" class="mr-2" size="20">mdi-image-multiple-outline</v-icon>
                  <span class="text-body-2 font-weight-bold">Evidencias Adjuntas:</span>
                  <v-spacer></v-spacer>
                  <v-chip color="accent" size="small" class="font-weight-bold px-3">
                    {{ infoDestino.evidencias_count }}
                  </v-chip>
                </div>
              </v-card>

              <!-- Botones de Acción Mágicos -->
              <v-btn
                color="primary"
                size="x-large"
                block
                class="mb-3 text-none font-weight-bold shadow-btn"
                rounded="pill"
                @click="capturarEvidencia('CAMERA')"
                :disabled="subiendo"
                height="56"
              >
                <v-icon left class="mr-2" size="24">mdi-camera</v-icon>
                Tomar Evidencia
              </v-btn>

              <v-btn
                color="error"
                size="x-large"
                block
                class="mb-3 text-none font-weight-bold shadow-btn"
                rounded="pill"
                @click="dispararVideo"
                :disabled="subiendo"
                height="56"
              >
                <v-icon left class="mr-2" size="24">mdi-video</v-icon>
                Grabar Video
              </v-btn>

              <v-btn
                color="secondary"
                variant="outlined"
                size="x-large"
                block
                class="mb-6 text-none font-weight-bold border-opacity-100"
                rounded="pill"
                @click="dispararGaleria"
                :disabled="subiendo"
                height="56"
                style="border-width: 2px;"
              >
                <v-icon left class="mr-2" size="24">mdi-folder-image</v-icon>
                Subir de Galería
              </v-btn>
              
              <!-- Input nativo invisible para video de cámara -->
              <input 
                type="file" 
                accept="video/*" 
                capture="environment" 
                ref="videoInput" 
                style="display: none" 
                @change="onArchivoSeleccionado"
              >

              <!-- Input nativo invisible para galería (fotos y videos) -->
              <input 
                type="file" 
                accept="image/*,video/*" 
                ref="galeriaInput" 
                style="display: none" 
                @change="onArchivoSeleccionado"
              >
              
              <v-btn
                color="grey-darken-2"
                variant="text"
                block
                class="text-none font-weight-bold"
                rounded="pill"
                @click="cancelar"
                :disabled="subiendo"
              >
                Volver / Terminar
              </v-btn>
            </div>
          </v-fade-transition>
        </v-card>

        <!-- Overlay de Carga Moderno -->
        <v-overlay
          :model-value="subiendo"
          class="align-center justify-center"
          persistent
          scrim="#0F172A"
          opacity="0.9"
        >
          <div class="text-center d-flex flex-column align-center px-4 loading-pulse">
            <v-progress-circular
              color="white"
              indeterminate
              size="70"
              width="5"
              class="mb-6"
            ></v-progress-circular>
            <span class="text-h5 text-white font-weight-black mb-1">{{ msjOverlay }}</span>
            <span class="text-body-2 text-grey-lighten-1">Asegurando la transmisión de datos...</span>
          </div>
        </v-overlay>

        <!-- Snackbar Premium -->
        <v-snackbar
          v-model="snackbar.show"
          :color="snackbar.color"
          timeout="4000"
          location="top"
          elevation="24"
          rounded="pill"
          class="mt-4"
        >
          <div class="d-flex align-center font-weight-medium">
            <v-icon :icon="snackbar.color === 'success' ? 'mdi-check-circle' : 'mdi-alert-circle'" class="mr-3" size="24"></v-icon>
            {{ snackbar.text }}
          </div>
        </v-snackbar>
      </v-container>
    </v-main>
  </v-app>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { Camera, CameraResultType, CameraSource } from '@capacitor/camera';
import axios from 'axios';

const defaultUrl = import.meta.env.VITE_BACKEND_URL || 'http://192.168.1.29:3000'; 
const mostrarConfig = ref(false);
const configUrl = ref(localStorage.getItem('BACKEND_URL') || defaultUrl);

const guardarConfig = () => {
  let urlStr = configUrl.value.trim();
  if (urlStr && !urlStr.startsWith('http')) urlStr = 'http://' + urlStr;
  if (!urlStr) urlStr = defaultUrl;
  localStorage.setItem('BACKEND_URL', urlStr);
  configUrl.value = urlStr;
  mostrarConfig.value = false;
  mostrarAlerta('Servidor actualizado a ' + urlStr, 'success');
};

const getBackendUrl = () => {
  return localStorage.getItem('BACKEND_URL') || defaultUrl;
};

// --- Sistema de Logs en Pantalla ---
const logs = ref([]);
const mostrarLogs = ref(false);

const interceptarLogs = () => {
  const oldLog = console.log;
  const oldError = console.error;
  
  console.log = function(...args) {
    const msg = args.map(a => typeof a === 'object' ? JSON.stringify(a) : a).join(' ');
    logs.value.unshift({ type: 'info', msg });
    oldLog.apply(console, args);
  };
  
  console.error = function(...args) {
    const msg = args.map(a => typeof a === 'object' ? JSON.stringify(a) : a).join(' ');
    logs.value.unshift({ type: 'error', msg });
    oldError.apply(console, args);
  };
};

onMounted(() => {
  interceptarLogs();
  console.log('App montada y sistema de captura de logs activo.');
  console.log('Servidor actual configurado en:', getBackendUrl());
});
// ------------------------------------

const codigo = ref('');
const subiendo = ref(false);
const msjOverlay = ref('Procesando...');

const paso = ref(1);
const infoDestino = ref(null);

const snackbar = ref({
  show: false,
  text: '',
  color: 'success'
});

const videoInput = ref(null);
const galeriaInput = ref(null);

const dispararVideo = () => {
  if (videoInput.value) {
    videoInput.value.click();
  }
};

const dispararGaleria = () => {
  if (galeriaInput.value) {
    galeriaInput.value.click();
  }
};

const onArchivoSeleccionado = async (event) => {
  const file = event.target.files[0];
  if (!file) return;

  const isVideo = file.type.startsWith('video/');
  msjOverlay.value = isVideo ? 'Subiendo video... (puede demorar)' : 'Subiendo imagen...';
  subiendo.value = true;
  
  try {
    const cod = codigo.value.toUpperCase();
    const formData = new FormData();
    formData.append('file', file, file.name);
    formData.append('con_audio', isVideo ? 'true' : 'false');
    
    await axios.post(`${getBackendUrl()}/mobile-sync/link/${cod}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: isVideo ? 120000 : 60000 // 120s para video, 60s para fotos
    });
    
    mostrarAlerta(isVideo ? '¡Video subido con éxito!' : '¡Imagen subida con éxito!', 'success');
    infoDestino.value.evidencias_count++; 
  } catch (error) {
    console.error('Error procesando archivo:', error);
    let msj = 'Error de red o timeout';
    if (error.response?.data?.message) {
      msj = Array.isArray(error.response.data.message) 
        ? error.response.data.message.join(', ') 
        : error.response.data.message;
    } else if (error.message) {
      msj = error.message;
    }
    mostrarAlerta('Falló la subida: ' + msj);
  } finally {
    subiendo.value = false;
    event.target.value = ''; // Limpiar input para permitir seleccionar el mismo archivo de nuevo
  }
};

const mostrarAlerta = (texto, color = 'error') => {
  snackbar.value = { show: true, text: texto, color };
};

const cancelar = () => {
  paso.value = 1;
  codigo.value = '';
  infoDestino.value = null;
};

/**
 * Paso 1: Valida el código y obtiene el resumen de la base de datos
 */
const buscarDestino = async () => {
  msjOverlay.value = 'Buscando destino...';
  subiendo.value = true;
  
  try {
    const cod = codigo.value.toUpperCase();
    const response = await axios.get(`${getBackendUrl()}/mobile-sync/validate/${cod}`);
    
    infoDestino.value = response.data;
    paso.value = 2;
    
  } catch (error) {
    console.error('Error validando:', error);
    codigo.value = '';
    
    let msj = 'Error de red o timeout';
    if (error.response?.data?.message) {
      msj = Array.isArray(error.response.data.message) 
        ? error.response.data.message.join(', ') 
        : error.response.data.message;
    } else if (error.message) {
      msj = error.message;
    }
    
    mostrarAlerta(msj);
  } finally {
    subiendo.value = false;
  }
};

/**
 * Paso 2: Activa el plugin de cámara
 */
const capturarEvidencia = async () => {
  try {
    // Configuración estricta para aligerar la carga de red sin compresión JS
    const photo = await Camera.getPhoto({
      quality: 60,                   // Calidad media para reducir peso final
      allowEditing: false,
      resultType: CameraResultType.Uri, // Retorna la URI nativa, muy rápido
      source: CameraSource.Camera,   // Solo cámara fotográfica
      width: 1280,                   // Límite HD para evitar 4K/1080p pesados
      height: 720,
      saveToGallery: false
    });

    if (photo.webPath || photo.path) {
      await procesarYSubir(photo);
    }
  } catch (error) {
    // Ignorar si el usuario simplemente canceló la cámara
    if (error.message !== 'User cancelled photos app' && error.message !== 'User cancelled') {
      mostrarAlerta('Error de cámara: ' + error.message);
    }
  }
};

/**
 * Sube el archivo y lo vincula al destino previamente validado
 */
const procesarYSubir = async (photoData) => {
  msjOverlay.value = 'Subiendo evidencia...';
  subiendo.value = true; // Bloqueo UI INMEDIATO
  
  try {
    const cod = codigo.value.toUpperCase();
    
    // 1. Convertir URI local a Blob nativo
    const response = await fetch(photoData.webPath);
    const blob = await response.blob();
    
    const extension = photoData.format || 'jpeg';
    const nombreArchivo = `mobile_${Date.now()}.${extension}`;
    
    // 2. Empaquetar FormData
    const formData = new FormData();
    formData.append('file', blob, nombreArchivo);
    formData.append('con_audio', 'false'); // Se puede expandir en el futuro
    
    // 3. Subir y vincular en una sola transacción en el backend
    await axios.post(`${getBackendUrl()}/mobile-sync/link/${cod}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000 // 60s timeout para redes locales lentas
    });
    
    mostrarAlerta('¡Evidencia subida! Puedes agregar otra.', 'success');
    infoDestino.value.evidencias_count++; 
    // NO llamamos a cancelar() para permitir múltiples subidas

  } catch (error) {
    console.error('Error procesando:', error);
    
    let msj = 'Error de red o timeout';
    if (error.response?.data?.message) {
      msj = Array.isArray(error.response.data.message) 
        ? error.response.data.message.join(', ') 
        : error.response.data.message;
    } else if (error.message) {
      msj = error.message;
    }
    
    mostrarAlerta('Fallo la operación: ' + msj);
    // Si falla la subida, NO cancelamos el paso 2, por si quieren reintentar tomar la foto
  } finally {
    subiendo.value = false; // Libera el v-overlay
  }
};
</script>

<style>
/* CSS Reset e Inyección de Fuentes Modernas */
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');

body {
  font-family: 'Outfit', sans-serif !important;
  margin: 0;
}
.v-application {
  font-family: 'Outfit', sans-serif !important;
}

/* Background Elegante (Gradiante sutil) */
.app-background {
  background: linear-gradient(135deg, #F1F5F9 0%, #E2E8F0 100%);
  min-height: 100vh;
}

/* Glassmorphism Effect para la Tarjeta Principal */
.glass-card {
  background: rgba(255, 255, 255, 0.9) !important;
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.4) !important;
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.08) !important;
}

/* Contenedor del Icono Superior */
.logo-container {
  width: 80px;
  height: 80px;
  background: linear-gradient(135deg, #3B82F6, #2563EB);
  border-radius: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 10px 25px rgba(59, 130, 246, 0.4);
  transform: rotate(-5deg);
  transition: transform 0.3s ease;
}
.glass-card:hover .logo-container {
  transform: rotate(0deg) scale(1.05);
}

/* Inputs y Botones Premium */
.custom-otp {
  letter-spacing: 4px;
}
.custom-otp .v-field {
  border-radius: 16px !important;
  box-shadow: 0 4px 6px rgba(0,0,0,0.02) !important;
}
.gradient-btn {
  background: linear-gradient(90deg, #0F172A 0%, #1E293B 100%) !important;
  color: white !important;
}
.shadow-btn {
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.2) !important;
  transition: all 0.2s ease;
}
.shadow-btn:active {
  transform: translateY(2px);
  box-shadow: 0 4px 10px rgba(15, 23, 42, 0.2) !important;
}

/* Diseño de la Tarjeta de Información */
.info-card {
  background-color: #F8FAFC !important;
  border-color: #E2E8F0 !important;
}
.info-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.info-item {
  display: flex;
  align-items: flex-start;
}
.info-desc {
  border-left-width: 3px !important;
}

/* Micro Animaciones */
.fade-in-up {
  animation: fadeInUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards;
  opacity: 0;
  transform: translateY(20px);
}
.delay-1 {
  animation-delay: 0.1s;
}
@keyframes fadeInUp {
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.loading-pulse {
  animation: pulseOpacity 1.5s infinite alternate;
}
@keyframes pulseOpacity {
  from { opacity: 0.8; }
  to { opacity: 1; }
}
</style>
