FROM eclipse-temurin:17-jre-jammy@sha256:e17d77fb030dd4b642dc078d048a5fb9efcb3676ee20305d905949105a6ccd5a

RUN groupadd --system --gid 10001 linsight \
    && useradd --system --uid 10001 --gid linsight --home-dir /nonexistent \
       --shell /usr/sbin/nologin linsight \
    && install -d -o linsight -g linsight /opt/linsight

WORKDIR /opt/linsight
COPY --chown=linsight:linsight ./target/linsight-gateway.jar app.jar

ENV TZ=Asia/Shanghai \
    JAVA_OPTS="-Xms512m -Xmx512m -Djava.security.egd=file:/dev/./urandom" \
    ARGS=""

USER 10001:10001
EXPOSE 48080

ENTRYPOINT ["sh", "-c", "exec java ${JAVA_OPTS} -jar app.jar ${ARGS}"]
