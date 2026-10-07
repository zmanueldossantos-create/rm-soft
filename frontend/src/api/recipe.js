// API calls for RecipeIngredient (Bill of Materials) management.
// Recipes are expressed PER BATCH (see Product.batch_yield) rather than
// per single unit - e.g. "1 saco de farinha per batch -> 400 paes".
import apiClient from './client';

export async function getRecipe(productId) {
  const res = await apiClient.get('/products/' + productId + '/recipe');
  return res.data;
}

// A recipe typed in any unit or package of each article (null = its base unit); the server keeps it in base units.
export async function setRecipe(productId, batchYield, ingredients, batchYieldSaleUnitId = null) {
  const res = await apiClient.put(`/products/${productId}/recipe`, {
    batch_yield: batchYield,
    batch_yield_sale_unit_id: batchYieldSaleUnitId,
    ingredients: ingredients.map((i) => ({
      ingredient_product_id: i.ingredientProductId, quantity_per_batch: i.quantityPerBatch, sale_unit_id: i.saleUnitId || null,
    })),
  });
  return res.data;
}
