// API calls for RecipeIngredient (Bill of Materials) management.
// Recipes are expressed PER BATCH (see Product.batch_yield) rather than
// per single unit - e.g. "1 saco de farinha per batch -> 400 paes".
import apiClient from './client';

export async function getRecipe(productId) {
  const res = await apiClient.get('/products/' + productId + '/recipe');
  return res.data;
}

export async function setRecipe(productId, batchYield, ingredients) {
  const res = await apiClient.put('/products/' + productId + '/recipe', {
    batch_yield: batchYield,
    ingredients: ingredients.map((i) => ({
      ingredient_product_id: i.ingredientProductId,
      quantity_per_batch: i.quantityPerBatch,
    })),
  });
  return res.data;
}
