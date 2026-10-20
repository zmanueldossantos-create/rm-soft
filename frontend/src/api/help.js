// The user guides (Ajuda) this user may read - written once on the server, read by the panel and the assistant.
import apiClient from './client';

export async function getHelpGuides() {
  const res = await apiClient.get('/help/guides');
  return res.data;
}
