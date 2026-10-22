-- Record currency with campaign-channel spend so cost metrics do not silently mix currencies.
alter table public.campaign_channels
  add column if not exists spend_currency char(3);
alter table public.campaign_channels
  drop constraint if exists campaign_channels_spend_currency_check;
alter table public.campaign_channels
  add constraint campaign_channels_spend_currency_check
  check (spend_currency is null or spend_currency ~ '^[A-Z]{3}$');
