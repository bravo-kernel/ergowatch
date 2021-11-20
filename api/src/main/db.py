import os
import asyncpg
import json


CONNECTION_POOL = None


async def init_connection_pool():
    global CONNECTION_POOL
    dbstr = f"postgresql://{os.environ['POSTGRES_PASSWORD']}:ergo@db/ergo"
    CONNECTION_POOL = await asyncpg.create_pool(dbstr)


async def get_latest_block_height():
    qry = "SELECT MAX(height) AS height FROM node_headers;"
    async with CONNECTION_POOL.acquire() as conn:
        row = await conn.fetchrow(qry)
    return row["height"]


async def get_latest_sync_height():
    qry = "select last_sync_height as height from ew.sync_status;"
    async with CONNECTION_POOL.acquire() as conn:
        row = await conn.fetchrow(qry)
    return row["height"]


async def get_oracle_pools_ergusd_latest():
    """
    Latest ERG/USD oracle pool posting
    """
    qry = """
        select height
            , price
            , datapoints
        from orp.ergusd_latest_posting_mv;
    """
    async with CONNECTION_POOL.acquire() as conn:
        row = await conn.fetchrow(qry)
    return dict(row)


async def get_oracle_pools_ergusd_recent_epoch_durations():
    qry = """
        select height as h
            , blocks as n
        from orp.ergusd_recent_epoch_durations_mv
        order by 1;
    """
    async with CONNECTION_POOL.acquire() as conn:
        rows = await conn.fetch(qry)
    return [dict(r) for r in rows]


async def get_oracle_pools_ergusd_oracle_stats():
    """
    ERG/USD oracle stats
    """
    qry = """
        select oracle_id
            , address
            , commits
            , accepted_commits
            , collections
            , first_commit
            , last_commit
            , last_accepted
            , last_collection
        from orp.ergusd_oracle_stats_mv
        order by 1;
    """
    async with CONNECTION_POOL.acquire() as conn:
        rows = await conn.fetch(qry)
    return [dict(r) for r in rows]


async def get_sigmausd_state():
    """
    Latest SigmaUSD bank state
    """
    qry = """
        with state as (
            select  (1 / oracle_price * 1000000000)::integer as peg_rate_nano
                , (reserves * 1000000000)::bigint as reserves
                , (circ_sigusd * 100)::integer as circ_sigusd
                , circ_sigrsv
                , net_sc_erg
                , net_rc_erg
            from sig.series_history_mv
            order by timestamp desc limit 1
        ), cumulative as (
            select cum_usd_erg_in as cum_sc_erg_in
                , cum_rsv_erg_in as cum_rc_erg_in
            from sig.history_transactions_cumulative
            order by bank_box_idx desc limit 1
        )
        select peg_rate_nano
            , reserves
            , circ_sigusd
            , circ_sigrsv
            , net_sc_erg
            , net_rc_erg
            , cum_sc_erg_in
            , cum_rc_erg_in
        from state, cumulative;
    """
    async with CONNECTION_POOL.acquire() as conn:
        row = await conn.fetchrow(qry)
    return dict(row)


async def get_sigmausd_sigrsv_ohlc_d():
    """
    SigRSV daily open high low close series.
    """
    qry = """
        select date as time
            , o as open
            , h as high
            , l as low
            , c as close
        from sig.sigrsv_ohlc_d_mv
        order by 1;
    """
    async with CONNECTION_POOL.acquire() as conn:
        rows = await conn.fetch(qry)
    return [dict(r) for r in rows]


async def get_sigmausd_history(days: int):
    """
    Last *days* of bank history.
    """
    qry = f"""
        select array_agg(timestamp order by timestamp) as timestamps
            , array_agg(oracle_price order by timestamp) as oracle_prices
            , array_agg(reserves order by timestamp) as reserves
            , array_agg(circ_sigusd order by timestamp) as circ_sigusd
            , array_agg(circ_sigrsv order by timestamp) as circ_sigrsv
        from sig.series_history_mv
        where timestamp >= (extract(epoch from now() - '{days} days'::interval))::bigint;
    """
    async with CONNECTION_POOL.acquire() as conn:
        row = await conn.fetchrow(qry)
    return dict(row)


async def get_sigmausd_history_full():
    """
    Full bank history.
    """
    qry = f"""
        select array_agg(timestamp order by timestamp) as timestamps
            , array_agg(oracle_price order by timestamp) as oracle_prices
            , array_agg(reserves order by timestamp) as reserves
            , array_agg(circ_sigusd order by timestamp) as circ_sigusd
            , array_agg(circ_sigrsv order by timestamp) as circ_sigrsv
        from sig.series_history_mv;
    """
    async with CONNECTION_POOL.acquire() as conn:
        row = await conn.fetchrow(qry)
    return dict(row)


async def get_metrics_preview():
    """
    Summary stats for metrics landing page.
    """
    qry = """
        select total_addresses
            , top100_supply_fraction,
            (
                select mean_age_ms / 1000. / 86400. as days
                from age.block_stats
                order by height desc limit 1
            ) as mean_age,
            (
                select boxes
                from dis.unspent_boxes
                order by timestamp desc limit 1
            ) as utxos
        from dis.preview;
    """
    async with CONNECTION_POOL.acquire() as conn:
        row = await conn.fetchrow(qry)
    return dict(row)


async def get_metrics_address_counts_summary():
    """
    Latest summary of address counts.
    """
    qry = f"""
        select label
            , latest
            , diff_1d
            , diff_1w
            , diff_4w
            , diff_6m
            , diff_1y
        from dis.address_counts_summary;
    """
    async with CONNECTION_POOL.acquire() as conn:
        rows = await conn.fetch(qry)
    return [dict(r) for r in rows]


async def get_metrics_addresses_series(days: int):
    """
    Last *days* days of addresses series.
    """
    qry = f"""
        select array_agg(dis.timestamp / 1000 order by dis.timestamp) as timestamps
            , array_agg(round(cgo.usd, 2) order by dis.timestamp) as ergusd
            , array_agg(total order by dis.timestamp) as total
            , array_agg(m_0_001 order by dis.timestamp) as m_0_001
            , array_agg(m_0_01 order by dis.timestamp) as m_0_01
            , array_agg(m_0_1 order by dis.timestamp) as m_0_1
            , array_agg(m_1 order by dis.timestamp) as m_1
            , array_agg(m_10 order by dis.timestamp) as m_10
            , array_agg(m_100 order by dis.timestamp) as m_100
            , array_agg(m_1k order by dis.timestamp) as m_1k
            , array_agg(m_10k order by dis.timestamp) as m_10k
            , array_agg(m_100k order by dis.timestamp) as m_100k
            , array_agg(m_1m order by dis.timestamp) as m_1m
        from dis.address_counts_by_minimal_balance dis
        left join cgo.price_at_first_of_day_block cgo
            on cgo.timestamp = dis.timestamp
        where dis.timestamp > (
            select timestamp
            from dis.address_counts_by_minimal_balance
            order by 1 desc
            limit 1 offset {days}
        );
    """
    async with CONNECTION_POOL.acquire() as conn:
        row = await conn.fetchrow(qry)
    return dict(row)


async def get_metrics_addresses_series_full():
    """
    Full addresses series.
    """
    qry = f"""
        select array_agg(dis.timestamp / 1000 order by dis.timestamp) as timestamps
            , array_agg(round(cgo.usd, 2) order by dis.timestamp) as ergusd
            , array_agg(total order by dis.timestamp) as total
            , array_agg(m_0_001 order by dis.timestamp) as m_0_001
            , array_agg(m_0_01 order by dis.timestamp) as m_0_01
            , array_agg(m_0_1 order by dis.timestamp) as m_0_1
            , array_agg(m_1 order by dis.timestamp) as m_1
            , array_agg(m_10 order by dis.timestamp) as m_10
            , array_agg(m_100 order by dis.timestamp) as m_100
            , array_agg(m_1k order by dis.timestamp) as m_1k
            , array_agg(m_10k order by dis.timestamp) as m_10k
            , array_agg(m_100k order by dis.timestamp) as m_100k
            , array_agg(m_1m order by dis.timestamp) as m_1m
        from dis.address_counts_by_minimal_balance dis
        left join cgo.price_at_first_of_day_block cgo
            on cgo.timestamp = dis.timestamp
        ;
    """
    async with CONNECTION_POOL.acquire() as conn:
        row = await conn.fetchrow(qry)
    return dict(row)


async def get_metrics_distribution_series(days: int):
    """
    Last *days* days of distribution series.
    """
    qry = f"""
        select array_agg(dis.timestamp / 1000 order by dis.timestamp) as timestamps
            , array_agg(round(cgo.usd, 2) order by dis.timestamp) as ergusd
            , array_agg(top10 order by dis.timestamp) as top10
            , array_agg(top100 order by dis.timestamp) as top100
            , array_agg(top1k order by dis.timestamp) as top1k
            , array_agg(top10k order by dis.timestamp) as top10k
            , array_agg(cexs order by dis.timestamp) as cexs
        from dis.top_addresses_supply dis
        left join cgo.price_at_first_of_day_block cgo
            on cgo.timestamp = dis.timestamp
        where dis.timestamp > (
            select timestamp
            from dis.top_addresses_supply
            order by 1 desc
            limit 1 offset {days}
        );
    """
    async with CONNECTION_POOL.acquire() as conn:
        row = await conn.fetchrow(qry)
    return dict(row)


async def get_metrics_distribution_series_full():
    """
    Full distribution series.
    """
    qry = f"""
        select array_agg(dis.timestamp / 1000 order by dis.timestamp) as timestamps
            , array_agg(round(cgo.usd, 2) order by dis.timestamp) as ergusd
            , array_agg(top10 order by dis.timestamp) as top10
            , array_agg(top100 order by dis.timestamp) as top100
            , array_agg(top1k order by dis.timestamp) as top1k
            , array_agg(top10k order by dis.timestamp) as top10k
            , array_agg(cexs order by dis.timestamp) as cexs
        from dis.top_addresses_supply dis
        left join cgo.price_at_first_of_day_block cgo
            on cgo.timestamp = dis.timestamp
        ;
    """
    async with CONNECTION_POOL.acquire() as conn:
        row = await conn.fetchrow(qry)
    return dict(row)
