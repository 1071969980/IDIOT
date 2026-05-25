{{/*
命名空间辅助模板
*/}}
{{- define "idiot.namespace" -}}
{{ .Values.namespacePrefix }}idiot
{{- end -}}

{{- define "idiot.namespaceUserSpace" -}}
{{ .Values.namespacePrefix }}idiot-user-space
{{- end -}}

{{- define "idiot.namespaceUserSpaceStorage" -}}
{{ .Values.namespacePrefix }}idiot-user-space-storage
{{- end -}}

{{/*
项目根目录 + 存储相对路径
*/}}
{{- define "idiot.storageBasePath" -}}
{{ .Values.projectRoot }}/{{ .Values.storage.relativePath }}{{ if .Values.storage.volumeSubPath }}/{{ .Values.storage.volumeSubPath }}{{ end }}
{{- end -}}

{{/*
Nginx SSL 证书完整路径
*/}}
{{- define "idiot.nginxSslPath" -}}
{{ .Values.projectRoot }}/{{ .Values.nginx.sslRelativePath }}
{{- end -}}

{{/*
通用标签
*/}}
{{- define "idiot.labels" -}}
app.kubernetes.io/name: idiot
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
