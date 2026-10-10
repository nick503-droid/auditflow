# backend/Dockerfile
FROM node:20-alpine

WORKDIR /usr/src/app

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

# El publicador construye desde git archive del SHA exacto. La identidad queda
# dentro de la imagen; recrear el contenedor sin exportar variables no la pierde.
ARG AUDITFLOW_DEPLOY_COMMIT=development
RUN node -e "const commit=process.argv[1]; if(commit !== 'development' && !/^[a-f0-9]{40}$/.test(commit)) process.exit(1); require('fs').writeFileSync('deployment.json', JSON.stringify({commit}));" "$AUDITFLOW_DEPLOY_COMMIT"
LABEL org.opencontainers.image.revision=$AUDITFLOW_DEPLOY_COMMIT

EXPOSE 3000

# Arrancar en modo producción
CMD ["npm", "run", "start:prod"]
