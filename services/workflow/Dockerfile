# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Purpose: reproducibly build the Flowable REST engine from the checked-in Maven source.
FROM maven:3.9.9-eclipse-temurin-21-alpine AS build
WORKDIR /src
COPY services/workflow/pom.xml .
RUN mvn -B -ntp dependency:go-offline
COPY services/workflow/src ./src
RUN mvn -B -ntp -DskipTests package

FROM eclipse-temurin:21-jre-alpine
WORKDIR /opt/bidweave
COPY --from=build /src/target/bidweave-workflow-1.0.0.jar app.jar
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65 -Xms192m -Xmx384m"
EXPOSE 8080
USER 10001
ENTRYPOINT ["java", "-jar", "/opt/bidweave/app.jar"]
