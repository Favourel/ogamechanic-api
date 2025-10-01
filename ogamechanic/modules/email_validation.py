import re
import requests
from typing import List, Optional
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class DisposableEmailValidator:
    """
    Validates email addresses against known disposable email domains.
    Uses both local list and multiple external APIs for validation.
    """
    # Common disposable email domains
    DISPOSABLE_DOMAINS = {
        'tempmail.com', 'mailinator.com', 'guerrillamail.com',
        '10minutemail.com', 'yopmail.com', 'temp-mail.org',
        'sharklasers.com', 'guerrillamail.info', 'guerrillamail.biz',
        'guerrillamail.com', 'guerrillamail.de', 'guerrillamail.net',
        'guerrillamail.org', 'guerrillamailblock.com', 'spam4.me',
        'trashmail.com', 'trashmail.me', 'trashmail.net', 'trashmail.org',
        'trashmail.ws', 'trashmailer.com', 'trashymail.com', 'trashymail.net',
        'tempmail.net', 'tempmail.org', 'tempmail.com', 'tempmail.de',
        'tempmail.fr', 'tempmail.it', 'tempmail.ru', 'tempmail.co.uk',
        'tempmail.co', 'tempmail.com.au', 'tempmail.com.br', 'tempmail.com.cn',
        'tempmail.com.hk', 'tempmail.com.my', 'tempmail.com.sg', 'tempmail.com.tw', # noqa
        'tempmail.com.vn', 'tempmail.de', 'tempmail.es', 'tempmail.fr',
        'tempmail.it', 'tempmail.jp', 'tempmail.kr', 'tempmail.nl',
        'tempmail.pl', 'tempmail.pt', 'tempmail.ru', 'tempmail.se',
        'tempmail.sg', 'tempmail.tw', 'tempmail.uk', 'tempmail.us',
        'tempmail.vn', 'tempmail.ws', 'tempmail.xyz', 'tempmail.zone',
        'tempmailapp.com', 'tempmailapp.net', 'tempmailapp.org',
        'tempmailapp.co', 'tempmailapp.co.uk', 'tempmailapp.com.au',
        'tempmailapp.com.br', 'tempmailapp.com.cn', 'tempmailapp.com.hk',
        'tempmailapp.com.my', 'tempmailapp.com.sg', 'tempmailapp.com.tw',
        'tempmailapp.com.vn', 'tempmailapp.de', 'tempmailapp.es',
        'tempmailapp.fr', 'tempmailapp.it', 'tempmailapp.jp',
        'tempmailapp.kr', 'tempmailapp.nl', 'tempmailapp.pl',
        'tempmailapp.pt', 'tempmailapp.ru', 'tempmailapp.se',
        'tempmailapp.sg', 'tempmailapp.tw', 'tempmailapp.uk',
        'tempmailapp.us', 'tempmailapp.vn', 'tempmailapp.ws',
        'tempmailapp.xyz', 'tempmailapp.zone'
    }

    # API endpoints for disposable email validation
    API_ENDPOINTS = {
        # 'disposable_email_detector': {
        #     'url': 'https://api.disposable-email-detector.com/v1/check',
        #     'method': 'GET',
        #     'params': {'domain': '{domain}'},
        #     'headers': {'Authorization': 'Bearer {api_key}'},
        #     'response_key': 'is_disposable'
        # },
        # 'email_validator': {
        #     'url': 'https://api.email-validator.net/api/verify',
        #     'method': 'GET',
        #     'params': {
        #         'EmailAddress': '{domain}',
        #         'APIKey': '{api_key}'
        #     },
        #     'response_key': 'Disposable'
        # },
        'abstract_api': {
            'url': 'https://emailvalidation.abstractapi.com/v1/',
            'method': 'GET',
            'params': {
                'api_key': '{api_key}',
                'email': '{domain}'
            },
            'response_key': 'is_disposable_email'
        }
    }

    def __init__(self, use_api: bool = True, cache_timeout: int = 3600):
        """
        Initialize the validator.
        
        Args:
            use_api (bool): Whether to use external API for validation
            cache_timeout (int): Cache timeout in seconds for API results
        """
        self.use_api = use_api
        self.cache_timeout = cache_timeout
        self.api_keys = {
            # 'disposable_email_detector': getattr(
            #     settings, 'DISPOSABLE_EMAIL_API_KEY', None
            # ),
            # 'email_validator': getattr(
            #     settings, 'EMAIL_VALIDATOR_API_KEY', None
            # ),
            'abstract_api': getattr(
                settings, 'ABSTRACT_API_KEY', None
            )
        }

    def validate_email(self, email: str) -> bool:
        """
        Validate an email address against disposable email domains.
        
        Args:
            email (str): Email address to validate
            
        Returns:
            bool: True if email is valid, False if it's disposable
            
        Raises:
            ValidationError: If email format is invalid
        """
        if not self._is_valid_email_format(email):
            raise ValidationError(_('Invalid email format'))

        domain = self._extract_domain(email)
        
        # Check local list first
        if domain in self.DISPOSABLE_DOMAINS:
            return False
            
        # Check cache
        cache_key = f'disposable_email_{domain}'
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result
            
        # Check APIs if enabled
        if self.use_api:
            for api_name, api_config in self.API_ENDPOINTS.items():
                api_key = self.api_keys.get(api_name)
                if not api_key:
                    continue
                    
                try:
                    is_valid = self._check_api(domain, api_name, api_config, api_key) # noqa
                    if is_valid is not None:  # API check was successful
                        cache.set(cache_key, is_valid, self.cache_timeout)
                        return is_valid
                except Exception:
                    continue  # Try next API if current one fails
            
        return True  # Default to allowing the email if all checks fail

    def _is_valid_email_format(self, email: str) -> bool:
        """Check if email format is valid."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def _extract_domain(self, email: str) -> str:
        """Extract domain from email address."""
        return email.split('@')[-1].lower()

    def _check_api(
        self, domain: str, api_name: str, api_config: dict, api_key: str
    ) -> Optional[bool]:
        """
        Check domain against external API.
        
        Args:
            domain (str): Domain to check
            api_name (str): Name of the API to use
            api_config (dict): API configuration
            api_key (str): API key for the service
            
        Returns:
            Optional[bool]: True if domain is valid, False if it's disposable,
                          None if check failed
        """
        try:
            # Prepare request parameters
            url = api_config['url']
            params = {
                k: v.format(domain=domain, api_key=api_key)
                for k, v in api_config['params'].items()
            }
            headers = {
                k: v.format(api_key=api_key)
                for k, v in api_config.get('headers', {}).items()
            }
            
            # Make request
            response = requests.request(
                api_config['method'],
                url,
                params=params,
                headers=headers,
                timeout=5
            )
            response.raise_for_status()
            data = response.json()
            
            # Extract result based on API response format
            is_disposable = data.get(api_config['response_key'])
            return not is_disposable if is_disposable is not None else None
            
        except (requests.RequestException, ValueError, KeyError):
            return None

    @classmethod
    def add_disposable_domain(cls, domain: str) -> None:
        """Add a domain to the disposable domains list."""
        cls.DISPOSABLE_DOMAINS.add(domain.lower())

    @classmethod
    def remove_disposable_domain(cls, domain: str) -> None:
        """Remove a domain from the disposable domains list."""
        cls.DISPOSABLE_DOMAINS.discard(domain.lower())

    @classmethod
    def get_disposable_domains(cls) -> List[str]:
        """Get list of all disposable domains."""
        return sorted(list(cls.DISPOSABLE_DOMAINS)) 