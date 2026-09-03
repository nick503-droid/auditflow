<template>
  <v-app>
    <v-main class="bg-grey-lighten-4">
      <v-container class="fill-height d-flex flex-column justify-center align-center">
        
        <!-- Tarjeta Principal -->
        <v-card class="pa-6 rounded-xl shadow-lg w-100" max-width="400" elevation="4">
          <div class="text-center mb-6">
            <v-icon icon="mdi-shield-check" size="64" color="primary" class="mb-2"></v-icon>
            <h1 class="text-h4 font-weight-bold text-primary">AuditFlow</h1>
            <p class="text-subtitle-1 text-grey-darken-1">Captura de Evidencias</p>
          </div>

          <!-- Código de Vinculación (OTP Style) -->
          <v-card-text>
            <div class="text-center mb-4">
              <span class="text-body-2 font-weight-bold text-grey-darken-2">CÓDIGO DE VINCULACIÓN</span>
            </div>
            
            <v-otp-input
              v-model="codigo"
              length="6"
              variant="outlined"
              class="mb-6"
              style="text-transform: uppercase;"
            ></v-otp-input>

            <v-divider class="mb-6"></v-divider>

            <!-- Botones de Acción Multimedia -->
            <v-btn
              block
              color="primary"
              size="x-large"
              class="mb-4 rounded-lg text-none font-weight-bold"
              prepend-icon="mdi-camera"
              @click="capturarEvidencia('CAMERA')"
              :disabled="!codigoValido"
            >
              Cámara / Video
            </v-btn>

            <v-btn
              block
              color="secondary"
              size="x-large"
              class="rounded-lg text-none font-weight-bold"
              prepend-icon="mdi-image-multiple"
              variant="tonal"
              @click="capturarEvidencia('PHOTOS')"
              :disabled="!codigoValido"
            >
              Subir desde Galería
            </v-btn>
          </v-card-text>
        </v-card>

        <!-- Overlay de Carga: Prevención de Congelamiento -->
        <v-overlay
          :model-value="subiendo"
          class="align-center justify-center"
          persistent
          scrim="black"
          opacity="0.8"
        >
          <div class="text-center d-flex flex-column align-center px-4">
            <v-progress-circular
              color="primary"
              indeterminate
              size="80"
              width="6"
              class="mb-6"
            ></v-progress-circular>
            <span class="text-h6 text-white font-weight-bold">Subiendo evidencia...</span>
            <span class="text-body-1 text-grey-lighten-2 mt-2">Por favor, no cierre la app.</span>
          </div>
        </v-overlay>

        <!-- Snackbar: Manejo de Errores y Éxito -->
        <v-snackbar
          v-model="snackbar.show"
          :color="snackbar.color"
          timeout="4000"
          location="bottom"
          elevation="24"
        >
          <div class="d-flex align-center">
            <v-icon :icon="snackbar.color === 'success' ? 'mdi-check-circle' : 'mdi-alert-circle'" class="mr-2"></v-icon>
            {{ snackbar.text }}
          </div>
          <template v-slot:actions>
            <v-btn variant="text" @click="snackbar.show = false">OK</v-btn>
          </template>
        </v-snackbar>
      </v-container>
    </v-main>
  </v-app>
</template>

<script setup>
import { ref, computed } from 'vue';
import { Camera, CameraResultType, CameraSource } from '@capacitor/camera';
import axios from 'axios';

// Estado Reactivo
const codigo = ref('');
const subiendo = ref(false);
const snackbar = ref({
  show: false,
  text: '',
  color: 'success'
});

// Validación Computada
const codigoValido = computed(() => codigo.value.length === 6);

// Helper de Notificaciones
const mostrarAlerta = (texto, color = 'error') => {
  snackbar.value = { show: true, text: texto, color };
};

// URL Base de NestJS (⚠️ Modificar por tu IP local de Ubuntu/Desarrollo)
const BACKEND_URL = 'http://192.168.1.XX:3000'; 

/**
 * Invoca el plugin nativo de Capacitor Camera.
 * ESTRATEGIA 1: Limitación nativa desde el origen.
 */
const capturarEvidencia = async (sourceType) => {
  try {
    const source = sourceType === 'CAMERA' ? CameraSource.Camera : CameraSource.Photos;

    // Configuración estricta para aligerar la carga de red sin compresión JS
    const photo = await Camera.getPhoto({
      quality: 60,                   // Calidad media para reducir peso final
      allowEditing: false,
      resultType: CameraResultType.Uri, // Retorna la URI nativa, muy rápido
      source: source,
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
 * Transmisión asíncrona de datos vía Axios
 */
const procesarYSubir = async (photoData) => {
  subiendo.value = true; // Activa el v-overlay (Bloqueo UI)
  
  try {
    // 1. Convertir URI local a Blob nativo
    const response = await fetch(photoData.webPath);
    const blob = await response.blob();
    
    const extension = photoData.format || 'jpeg';
    const nombreArchivo = `mobile_${Date.now()}.${extension}`;
    
    // 2. Empaquetar FormData
    const formData = new FormData();
    formData.append('file', blob, nombreArchivo);
    
    // 3. Subir el binario al NestJS (StorageService)
    const uploadRes = await axios.post(`${BACKEND_URL}/uploads`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000 // 60s timeout para redes locales lentas
    });
    
    const evidenciaUrl = uploadRes.data.evidencia_url;
    
    // 4. Vincular el archivo subido a la bitácora activa (PATCH)
    // El código se pasa a mayúsculas para empatar con la base de datos
    await axios.patch(`${BACKEND_URL}/bitacoras/codigo/${codigo.value.toUpperCase()}/evidencia`, {
      evidencia_url: evidenciaUrl,
      con_audio: false // Asumimos false para fotos (se puede expandir para video)
    });

    mostrarAlerta('¡Evidencia vinculada exitosamente!', 'success');
    
    // Opcional: Limpiar el input para el siguiente código, o mantenerlo para subir múltiples
    // codigo.value = '';

  } catch (error) {
    console.error('Error subiendo:', error);
    const msj = error.response?.data?.message || error.message || 'Error de red o timeout';
    mostrarAlerta('Fallo la subida: ' + msj);
  } finally {
    subiendo.value = false; // Libera el v-overlay
  }
};
</script>

<style scoped>
/* Ajustes específicos si se requiere, Vuetify maneja el responsive por defecto */
.v-otp-input {
  letter-spacing: 4px;
}
</style>
