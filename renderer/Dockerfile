FROM mcr.microsoft.com/playwright:v1.64.1-noble
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY browser.js server.mjs ./
RUN npm run build && chown -R pwuser:pwuser /app
USER pwuser
ENV HOST=0.0.0.0 PORT=3001
EXPOSE 3001
CMD ["node","server.mjs"]
