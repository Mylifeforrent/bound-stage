FROM jenkins/jenkins:lts-jdk21

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl jq openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
USER jenkins

# Install only what these freestyle jobs need.  Jenkins core supplies the
# freestyle project, shell builder, BuildTrigger and artifact archiver.
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

# Seed the local-only security settings and the two jobs + their notifiers.
COPY init.groovy.d/ /usr/share/jenkins/ref/init.groovy.d/
COPY jobs/ /usr/share/jenkins/ref/jobs/
