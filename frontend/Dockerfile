# Interface Next.js (sortie « standalone » : image légère sans node_modules complet)
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
ARG HIPPO_API_URL=http://backend:8000
ENV HIPPO_API_URL=$HIPPO_API_URL NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S hippo && adduser -S hippo -G hippo
COPY --from=build --chown=hippo:hippo /app/.next/standalone ./
COPY --from=build --chown=hippo:hippo /app/.next/static ./.next/static
COPY --from=build --chown=hippo:hippo /app/public ./public
USER hippo
EXPOSE 3000
CMD ["node", "server.js"]
