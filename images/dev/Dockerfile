FROM ubuntu:24.04

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Update and install requested tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    byobu \
    tmux \
    npm \
    vim \
    zsh \
    curl \
    sudo \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set default shell
ENV SHELL=/usr/bin/zsh

# Create a workspace directory
WORKDIR /workspace

# Set default command to keep the container alive
CMD ["sleep", "infinity"]
