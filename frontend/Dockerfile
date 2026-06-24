# 前端 Dockerfile：多阶段构建
# 阶段一：构建产物
FROM node:20-alpine AS builder

WORKDIR /app

# 复制依赖声明文件
COPY package.json package-lock.json* ./

# 安装依赖
RUN npm ci || npm install

# 复制源代码
COPY . .

# 构建生产版本
RUN npm run build

# 阶段二：nginx 服务
FROM nginx:alpine AS runtime

# 复制自定义 nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 从构建阶段复制产物到 nginx 静态目录
COPY --from=builder /app/dist /usr/share/nginx/html

# 暴露端口
EXPOSE 80

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

# 启动 nginx
CMD ["nginx", "-g", "daemon off;"]
