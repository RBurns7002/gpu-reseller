import os, time
import stripe
STRIPE_KEY = os.getenv('STRIPE_SECRET','')
stripe.api_key = STRIPE_KEY

PRODUCT_IDS = { 'DGX Spark': os.getenv('STRIPE_PROD_DGX','prod_xxx') }
PRICE_IDS   = { 'DGX Spark': os.getenv('STRIPE_PRICE_DGX','price_xxx') }

def report_usage(subscription_item_id: str, quantity: int, timestamp=None):
    if not STRIPE_KEY:
        return {'mock': True, 'quantity': quantity}
    ts = int(timestamp or time.time())
    return stripe.UsageRecord.create(quantity=quantity,timestamp=ts,action='increment',subscription_item=subscription_item_id)
