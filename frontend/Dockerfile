FROM node:20-alpine AS builder
WORKDIR /app
# package-lock.json required for npm ci (see README)
COPY package.json package-lock.json ./
RUN npm ci
# .dockerignore excludes host node_modules/dist — do not copy those into the image
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
