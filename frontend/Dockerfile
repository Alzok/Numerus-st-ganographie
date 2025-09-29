FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install || true

COPY . .

ENV HOST=0.0.0.0

EXPOSE 3000

CMD ["sh", "-c", "npm install && npm run dev"]
