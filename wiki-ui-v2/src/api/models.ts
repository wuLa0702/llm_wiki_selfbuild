import { fetchJson, postJson, putJson, deleteJson } from '@/api/client';

export interface ModelConfig {
  id: number;
  name: string;
  provider: string;
  model_name: string;
  api_key: string;
  api_base: string;
  is_active: boolean;
  sort_order: number;
}

export interface ModelConfigCreate {
  name: string;
  provider?: string;
  model_name: string;
  api_key?: string;
  api_base?: string;
  is_active?: boolean;
  sort_order?: number;
}

export interface ModelConfigUpdate {
  name?: string;
  provider?: string;
  model_name?: string;
  api_key?: string;
  api_base?: string;
  is_active?: boolean;
  sort_order?: number;
}

export function listModels(): Promise<{ models: ModelConfig[] }> {
  return fetchJson('/v1/models');
}

export function getModel(id: number): Promise<ModelConfig> {
  return fetchJson(`/v1/models/${id}`);
}

export function createModel(data: ModelConfigCreate): Promise<ModelConfig> {
  return postJson('/v1/models', data);
}

export function updateModel(id: number, data: ModelConfigUpdate): Promise<ModelConfig> {
  return putJson(`/v1/models/${id}`, data);
}

export function deleteModel(id: number): Promise<{ status: string; deleted_id: number }> {
  return deleteJson(`/v1/models/${id}`);
}
