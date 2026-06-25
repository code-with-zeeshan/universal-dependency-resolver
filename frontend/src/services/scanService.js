import apiClient from './apiClient'

export default {
  async scanGithub(repoUrl, branch = 'main') {
    const resp = await apiClient.post('/scan/github', { repo_url: repoUrl, branch })
    return resp.data
  },

  async scanUpload(file) {
    const form = new FormData()
    form.append('file', file)
    const resp = await apiClient.post('/scan/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return resp.data
  },

  async scanLocal(directoryPath) {
    const resp = await apiClient.post('/scan/local', { directory_path: directoryPath })
    return resp.data
  },
}
