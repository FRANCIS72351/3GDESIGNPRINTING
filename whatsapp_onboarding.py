"""
3G DESIGN — Meta WhatsApp Embedded Signup (OAuth code exchange).
https://developers.facebook.com/docs/whatsapp/embedded-signup
"""
import os
from datetime import datetime, timedelta

import requests

from whatsapp_credentials import save_integration

GRAPH_API = 'https://graph.facebook.com/v21.0'


def _app_credentials():
    app_id = os.getenv('META_APP_ID', '').strip()
    app_secret = os.getenv('META_APP_SECRET', '').strip()
    if not app_id or not app_secret:
        raise ValueError('META_APP_ID and META_APP_SECRET must be set in .env')
    return app_id, app_secret


def exchange_code_for_token(code):
    """Exchange Embedded Signup authorization code for a user access token."""
    app_id, app_secret = _app_credentials()
    resp = requests.get(
        f'{GRAPH_API}/oauth/access_token',
        params={
            'client_id': app_id,
            'client_secret': app_secret,
            'code': code,
        },
        timeout=30,
    )
    data = resp.json()
    if not resp.ok or 'access_token' not in data:
        raise ValueError(data.get('error', {}).get('message', resp.text or 'Token exchange failed'))
    return data


def exchange_for_long_lived_token(short_lived_token):
    """Convert short-lived token to ~60-day long-lived token."""
    app_id, app_secret = _app_credentials()
    resp = requests.get(
        f'{GRAPH_API}/oauth/access_token',
        params={
            'grant_type': 'fb_exchange_token',
            'client_id': app_id,
            'client_secret': app_secret,
            'fb_exchange_token': short_lived_token,
        },
        timeout=30,
    )
    data = resp.json()
    if resp.ok and data.get('access_token'):
        return data
    return {'access_token': short_lived_token, 'expires_in': 3600}


def _graph_get(path, token, params=None):
    resp = requests.get(
        f'{GRAPH_API}/{path.lstrip("/")}',
        params={**(params or {}), 'access_token': token},
        timeout=30,
    )
    return resp.json() if resp.ok else {}


def discover_waba_and_phone(access_token, hint_waba_id='', hint_phone_id=''):
    """
    Resolve WABA ID and Phone Number ID from Embedded Signup hints or Graph API.
    """
    waba_id = (hint_waba_id or '').strip()
    phone_number_id = (hint_phone_id or '').strip()
    display_phone = ''
    business_name = ''

    if waba_id and not phone_number_id:
        phones = _graph_get(f'{waba_id}/phone_numbers', access_token, {'fields': 'id,display_phone_number,verified_name'})
        for p in phones.get('data', []):
            phone_number_id = p.get('id', '')
            display_phone = p.get('display_phone_number', '')
            business_name = p.get('verified_name', '')
            if phone_number_id:
                break

    if not waba_id:
        debug = _graph_get(
            'debug_token',
            f"{os.getenv('META_APP_ID')}:{os.getenv('META_APP_SECRET')}",
            {'input_token': access_token},
        )
        granular = debug.get('data', {}).get('granular_scopes', [])
        for scope in granular:
            if scope.get('scope') == 'whatsapp_business_management':
                targets = scope.get('target_ids', [])
                if targets:
                    waba_id = str(targets[0])
                    break

    if waba_id and not phone_number_id:
        phones = _graph_get(f'{waba_id}/phone_numbers', access_token, {'fields': 'id,display_phone_number,verified_name'})
        for p in phones.get('data', []):
            phone_number_id = p.get('id', '')
            display_phone = p.get('display_phone_number', '')
            business_name = p.get('verified_name', '')
            if phone_number_id:
                break

    if not phone_number_id:
        raise ValueError(
            'Could not resolve Phone Number ID. Complete Embedded Signup in Meta, '
            'or pass phone_number_id from the WA_EMBEDDED_SIGNUP event.'
        )

    return {
        'waba_id': waba_id,
        'phone_number_id': phone_number_id,
        'display_phone': display_phone,
        'business_name': business_name,
    }


def subscribe_app_to_waba(waba_id, access_token):
    """Subscribe this Meta app to receive webhooks for the WABA."""
    if not waba_id:
        return False, 'No WABA ID'
    resp = requests.post(
        f'{GRAPH_API}/{waba_id}/subscribed_apps',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=30,
    )
    if resp.ok:
        return True, resp.json()
    return False, resp.text


def complete_embedded_signup(*, code, connected_by='', waba_id='', phone_number_id=''):
    """
    Full onboarding: code → long-lived token → discover IDs → save → subscribe webhooks.
    """
    short = exchange_code_for_token(code)
    long_lived = exchange_for_long_lived_token(short['access_token'])
    access_token = long_lived['access_token']
    expires_in = long_lived.get('expires_in', 5184000)
    token_expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))

    account = discover_waba_and_phone(access_token, waba_id, phone_number_id)
    subscribe_app_to_waba(account['waba_id'], access_token)

    row = save_integration(
        access_token=access_token,
        phone_number_id=account['phone_number_id'],
        waba_id=account.get('waba_id', ''),
        display_phone=account.get('display_phone', ''),
        business_name=account.get('business_name', ''),
        connected_by=connected_by,
        connection_method='embedded_signup',
        token_expires_at=token_expires_at,
    )
    return {
        'status': 'success',
        'phone_number_id': row.phone_number_id,
        'waba_id': row.waba_id,
        'display_phone': row.display_phone,
        'business_name': row.business_name,
        'connected_at': row.connected_at.isoformat() if row.connected_at else None,
    }
