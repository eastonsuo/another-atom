FROM alpine:3.22

RUN apk add --no-cache vim
COPY vimrc /etc/another-atom/vimrc

USER 65534:65534
WORKDIR /workspace
CMD ["vim", "-Z", "-n", "-u", "/etc/another-atom/vimrc", "/workspace/app-spec.json"]
