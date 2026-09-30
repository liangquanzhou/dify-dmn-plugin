FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn --batch-mode --no-transfer-progress dependency:go-offline
COPY src ./src
RUN mvn --batch-mode --no-transfer-progress -DskipTests package

FROM eclipse-temurin:21-jre-jammy
RUN groupadd --gid 10001 dmn && useradd --uid 10001 --gid dmn --no-create-home --shell /usr/sbin/nologin dmn
WORKDIR /app
COPY --from=build --chown=10001:10001 /build/target/dmn-engine-service.jar /app/service.jar
USER 10001:10001
ENV DMN_BIND_HOST=0.0.0.0 PORT=8080 DMN_ENV=production
EXPOSE 8080
ENTRYPOINT ["java","-XX:MaxRAMPercentage=65","-XX:+ExitOnOutOfMemoryError","-jar","/app/service.jar"]
