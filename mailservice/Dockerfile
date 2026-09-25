# =============================================================================
# O2OA 本地邮件验证码服务（x_sms_assemble_control 平替）
#
# 设计要点：
#   1) 纯 Python 标准库实现 —— 无 pip 依赖，镜像小、构建快、无供应链风险。
#   2) 平台 linux/arm64 —— 本机为 ARM64，原生跑（amd64 亦可，走 QEMU 较慢）。
#   3) tzdata 必须装 —— 否则容器内 datetime.now() 是 UTC，日志时间戳与宿主差 8 小时，
#      排查问题时会误判（本机历史上已因此踩过坑）。
#   4) 非 root 运行；/data 为唯一可写目录（挂载卷），代码目录只读。
# =============================================================================
FROM python:3.13-alpine

LABEL org.opencontainers.image.title="o2oa-mailservice" \
      org.opencontainers.image.description="O2OA 本地邮件验证码服务（x_sms_assemble_control 平替），不依赖 O2 云平台" \
      org.opencontainers.image.version="1.0.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    O2OA_MAIL_DATA_DIR=/data

# 时区数据（见文件头第 3 条）
RUN apk add --no-cache tzdata \
 && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
 && echo "Asia/Shanghai" > /etc/timezone \
 && rm -rf /var/cache/apk/*

WORKDIR /app
COPY o2oa_mail_service.py /app/o2oa_mail_service.py

RUN addgroup -S o2oa \
 && adduser -S -G o2oa o2oa \
 && mkdir -p /data \
 && chown -R o2oa:o2oa /data /app
USER o2oa

VOLUME ["/data"]
EXPOSE 8095

# 健康检查只用标准库，不要求镜像里有 curl（alpine 默认没有）
HEALTHCHECK --interval=30s --timeout=8s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8095/api/health',timeout=5).status==200 else 1)"

ENTRYPOINT ["python", "-u", "/app/o2oa_mail_service.py"]
