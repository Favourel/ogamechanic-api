"""
Payment Service Module

This module provides comprehensive payment services including:
- Paystack integration for payments and transfers
- Wallet management and transaction processing
- Bank account verification and management
- Webhook handling and security
"""

import uuid
import hmac
import hashlib
import requests
from decimal import Decimal
from typing import Dict, Any, Tuple
from django.conf import settings
from django.utils import timezone
from django.db import transaction, models
from users.models import Wallet, Transaction, BankAccount
from users.services import NotificationService


class PaymentService:
    """Main payment service for handling all payment operations."""
    
    @staticmethod
    def initialize_paystack_payment(
        email: str,
        amount: Decimal,
        reference: str,
        callback_url: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Initialize a Paystack payment.
        
        Args:
            email: Customer email
            amount: Amount in NGN
            reference: Unique payment reference
            callback_url: Webhook callback URL
            metadata: Additional payment metadata
            
        Returns:
            Dict containing payment initialization response
        """
        headers = {
            'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json',
        }
        
        payload = {
            'email': email,
            'amount': int(amount * 100),  # Convert to kobo
            'reference': reference,
            'callback_url': callback_url,
        }
        
        if metadata:
            payload['metadata'] = metadata
            
        try:
            response = requests.post(
                'https://api.paystack.co/transaction/initialize',
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'data': response.json().get('data', {}),
                    'message': 'Payment initialized successfully'
                }
            else:
                return {
                    'success': False,
                    'message': f'Paystack error: {response.status_code}',
                    'data': response.json() if response.content else {}
                }
                
        except requests.RequestException as e:
            return {
                'success': False,
                'message': f'Network error: {str(e)}',
                'data': {}
            }
    
    @staticmethod
    def verify_paystack_payment(reference: str) -> Dict[str, Any]:
        """
        Verify a Paystack payment.
        
        Args:
            reference: Payment reference to verify
            
        Returns:
            Dict containing verification response
        """
        headers = {
            'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        }
        
        try:
            response = requests.get(
                f'https://api.paystack.co/transaction/verify/{reference}',
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'data': response.json().get('data', {}),
                    'message': 'Payment verified successfully'
                }
            else:
                return {
                    'success': False,
                    'message': f'Verification failed: {response.status_code}',
                    'data': response.json() if response.content else {}
                }
                
        except requests.RequestException as e:
            return {
                'success': False,
                'message': f'Network error: {str(e)}',
                'data': {}
            }
    
    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str) -> bool:
        """
        Verify Paystack webhook signature.
        
        Args:
            payload: Raw webhook payload
            signature: Webhook signature header
            
        Returns:
            True if signature is valid, False otherwise
        """
        expected_signature = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    
    @staticmethod
    def resolve_bank_account(account_number: str, bank_code: str) -> Dict[str, Any]: # noqa
        """
        Resolve bank account details with Paystack.
        
        Args:
            account_number: Bank account number
            bank_code: Bank code
            
        Returns:
            Dict containing account resolution response
        """
        headers = {
            'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json',
        }
        
        payload = {
            'account_number': account_number,
            'bank_code': bank_code
        }
        
        try:
            response = requests.post(
                'https://api.paystack.co/bank/resolve',
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status'):
                    return {
                        'success': True,
                        'data': data.get('data', {}),
                        'message': 'Account resolved successfully'
                    }
                else:
                    return {
                        'success': False,
                        'message': data.get('message', 'Account resolution failed'), # noqa
                        'data': {}
                    }
            else:
                return {
                    'success': False,
                    'message': f'Resolution failed: {response.status_code}',
                    'data': response.json() if response.content else {}
                }
                
        except requests.RequestException as e:
            return {
                'success': False,
                'message': f'Network error: {str(e)}',
                'data': {}
            }
    
    @staticmethod
    def get_bank_list() -> Dict[str, Any]:
        """
        Get list of supported banks from Paystack.
        
        Returns:
            Dict containing bank list
        """
        headers = {
            'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        }
        
        try:
            response = requests.get(
                'https://api.paystack.co/bank',
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'data': response.json().get('data', []),
                    'message': 'Bank list retrieved successfully'
                }
            else:
                return {
                    'success': False,
                    'message': f'Failed to get bank list: {response.status_code}', # noqa
                    'data': []
                }
                
        except requests.RequestException as e:
            return {
                'success': False,
                'message': f'Network error: {str(e)}',
                'data': []
            }


class WalletService:
    """Service for wallet operations."""
    
    @staticmethod
    def get_or_create_wallet(user) -> Wallet:
        """Get or create wallet for user."""
        wallet, created = Wallet.objects.get_or_create(user=user)
        return wallet
    
    @staticmethod
    def credit_wallet(wallet: Wallet, amount: Decimal, description: str = "Wallet credit") -> Transaction: # noqa
        """Credit wallet and create transaction record."""
        with transaction.atomic():
            wallet.credit(amount, description)
            return wallet.transactions.latest('created_at')
    
    @staticmethod
    def debit_wallet(wallet: Wallet, amount: Decimal, description: str = "Wallet debit") -> Transaction: # noqa
        """Debit wallet and create transaction record."""
        with transaction.atomic():
            wallet.debit(amount, description)
            return wallet.transactions.latest('created_at')
    
    @staticmethod
    def can_transact(wallet: Wallet, amount: Decimal) -> Tuple[bool, str]:
        """Check if wallet can perform transaction."""
        return wallet.can_transact(amount)
    
    @staticmethod
    def get_transaction_summary(wallet: Wallet, days: int = 30) -> Dict[str, Any]: # noqa
        """Get wallet transaction summary."""
        from django.utils import timezone
        from datetime import timedelta
        
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        transactions = wallet.transactions.filter(
            created_at__range=(start_date, end_date)
        )
        
        summary = {
            'total_transactions': transactions.count(),
            'total_credits': transactions.filter(
                transaction_type='credit'
            ).aggregate(
                total=models.Sum('amount')
            )['total'] or 0,
            'total_debits': transactions.filter(
                transaction_type='debit'
            ).aggregate(
                total=models.Sum('amount')
            )['total'] or 0,
            'net_flow': 0,
            'transaction_types': {},
            'daily_totals': {}
        }
        
        # Calculate net flow
        summary['net_flow'] = summary['total_credits'] - summary['total_debits'] # noqa
        
        # Transaction type breakdown
        for txn in transactions:
            txn_type = txn.transaction_type
            if txn_type not in summary['transaction_types']:
                summary['transaction_types'][txn_type] = 0
            summary['transaction_types'][txn_type] += float(txn.amount)
        
        # Daily totals
        for txn in transactions:
            date_str = txn.created_at.strftime('%Y-%m-%d')
            if date_str not in summary['daily_totals']:
                summary['daily_totals'][date_str] = 0
            summary['daily_totals'][date_str] += float(txn.amount)
        
        return summary


class BankAccountService:
    """Service for bank account operations."""
    
    @staticmethod
    def create_bank_account(user, account_number: str, account_name: str, bank_code: str) -> Tuple[BankAccount, bool]: # noqa
        """Create and verify bank account."""
        # Check if account already exists
        if BankAccount.objects.filter(
            user=user,
            account_number=account_number,
            bank_code=bank_code
        ).exists():
            return None, False
        
        # Resolve account with Paystack
        resolution = PaymentService.resolve_bank_account(account_number, bank_code) # noqa
        
        if resolution['success']:
            bank_name = resolution['data'].get('bank_name', 'Unknown Bank')
            verified_account_name = resolution['data'].get('account_name', account_name) # noqa
            
            bank_account = BankAccount.objects.create(
                user=user,
                account_number=account_number,
                account_name=verified_account_name,
                bank_code=bank_code,
                bank_name=bank_name,
                is_verified=True
            )
            return bank_account, True
        else:
            # Create unverified account
            bank_account = BankAccount.objects.create(
                user=user,
                account_number=account_number,
                account_name=account_name,
                bank_code=bank_code,
                bank_name='Unknown Bank',
                is_verified=False
            )
            return bank_account, False
    
    @staticmethod
    def verify_bank_account(bank_account: BankAccount) -> bool:
        """Verify existing bank account."""
        resolution = PaymentService.resolve_bank_account(
            bank_account.account_number,
            bank_account.bank_code
        )
        
        if resolution['success']:
            bank_account.account_name = resolution['data'].get('account_name', bank_account.account_name) # noqa
            bank_account.bank_name = resolution['data'].get('bank_name', bank_account.bank_name) # noqa
            bank_account.is_verified = True
            bank_account.save()
            return True
        
        return False


class TransactionService:
    """Service for transaction operations."""
    
    @staticmethod
    def create_transaction(
        wallet: Wallet,
        amount: Decimal,
        transaction_type: str,
        description: str = "",
        reference: str = None,
        metadata: Dict[str, Any] = None
    ) -> Transaction:
        """Create a new transaction."""
        if not reference:
            reference = f"{transaction_type.upper()}_{uuid.uuid4().hex[:8].upper()}" # noqa
        
        return Transaction.objects.create(
            wallet=wallet,
            amount=amount,
            transaction_type=transaction_type,
            description=description,
            reference=reference,
            metadata=metadata or {}
        )
    
    @staticmethod
    def process_wallet_topup(wallet: Wallet, amount: Decimal, payment_reference: str) -> Transaction: # noqa
        """Process wallet top-up transaction."""
        with transaction.atomic():
            # Create transaction record
            txn = TransactionService.create_transaction(
                wallet=wallet,
                amount=amount,
                transaction_type='top_up',
                description="Wallet top-up via Paystack",
                reference=payment_reference
            )
            
            # Credit wallet
            wallet.credit(amount, "Wallet top-up via Paystack")
            
            # Send notification
            NotificationService.create_notification(
                user=wallet.user,
                title="Wallet Top-up Successful",
                message=f"Your wallet has been credited with {amount} NGN",
                notification_type='success'
            )
            
            return txn
    
    @staticmethod
    def process_wallet_withdrawal(
        wallet: Wallet,
        amount: Decimal,
        bank_account: BankAccount,
        description: str = "Wallet withdrawal"
    ) -> Transaction:
        """Process wallet withdrawal transaction."""
        with transaction.atomic():
            # Check balance
            if wallet.balance < amount:
                raise ValueError("Insufficient balance")
            
            # Create transaction record
            txn = TransactionService.create_transaction(
                wallet=wallet,
                amount=amount,
                transaction_type='withdrawal',
                description=description,
                metadata={
                    'bank_account_id': str(bank_account.id),
                    'bank_name': bank_account.bank_name,
                    'account_number': bank_account.account_number
                }
            )
            
            # Debit wallet
            wallet.debit(amount, f"Withdrawal to {bank_account.get_display_name()}") # noqa
            
            # Send notification
            NotificationService.create_notification(
                user=wallet.user,
                title="Withdrawal Successful",
                message=f"Withdrawal of {amount} NGN to {bank_account.get_display_name()} has been processed", # noqa
                notification_type='success'
            )
            
            return txn


class WebhookService:
    """Service for handling webhooks."""
    
    @staticmethod
    def process_paystack_webhook(payload: Dict[str, Any]) -> bool:
        """Process Paystack webhook payload."""
        event = payload.get('event')
        data = payload.get('data', {})
        reference = data.get('reference')
        
        if not event or not reference:
            return False
        
        try:
            with transaction.atomic():
                if event == 'charge.success':
                    return WebhookService._handle_successful_charge(data)
                elif event == 'transfer.success':
                    return WebhookService._handle_successful_transfer(data)
                elif event == 'transfer.failed':
                    return WebhookService._handle_failed_transfer(data)
                else:
                    return True  # Ignore other events
        except Exception as e:
            # Log error
            from django.utils.log import logger
            logger.error(f"Webhook processing error: {e}")
            return False
    
    @staticmethod
    def _handle_successful_charge(data: Dict[str, Any]) -> bool:
        """Handle successful charge webhook."""
        reference = data.get('reference')
        amount = data.get('amount', 0) / 100  # Convert from kobo
        
        # Handle wallet top-up
        if reference.startswith('TOPUP_'):
            try:
                txn = Transaction.objects.select_for_update().get(
                    reference=reference,
                    status='pending'
                )
                
                if txn.transaction_type == 'top_up':
                    TransactionService.process_wallet_topup(
                        txn.wallet, amount, reference
                    )
                    return True
            except Transaction.DoesNotExist:
                pass
        
        # Handle order payment
        else:
            from products.models import Order
            try:
                order = Order.objects.select_for_update().get(
                    payment_reference=reference
                )
                if order.payment_status != 'paid':
                    order.payment_status = 'paid'
                    order.status = 'paid'
                    order.paid_at = timezone.now()
                    order.save()
                    return True
            except Order.DoesNotExist:
                pass
        
        return False
    
    @staticmethod
    def _handle_successful_transfer(data: Dict[str, Any]) -> bool:
        """Handle successful transfer webhook."""
        reference = data.get('reference')
        
        try:
            txn = Transaction.objects.select_for_update().get(
                reference=reference,
                status='processing'
            )
            
            if txn.transaction_type == 'withdrawal':
                txn.mark_as_completed()
                return True
        except Transaction.DoesNotExist:
            pass
        
        return False
    
    @staticmethod
    def _handle_failed_transfer(data: Dict[str, Any]) -> bool:
        """Handle failed transfer webhook."""
        reference = data.get('reference')
        failure_reason = data.get('failure_reason', 'Transfer failed')
        
        try:
            txn = Transaction.objects.select_for_update().get(
                reference=reference,
                status='processing'
            )
            
            if txn.transaction_type == 'withdrawal':
                txn.mark_as_failed(failure_reason)
                
                # Refund the wallet
                txn.wallet.credit(txn.amount, f"Refund for failed withdrawal: {failure_reason}") # noqa
                
                # Send notification
                NotificationService.create_notification(
                    user=txn.wallet.user,
                    title="Withdrawal Failed",
                    message=f"Your withdrawal of {txn.amount} NGN has failed. The amount has been refunded to your wallet.", # noqa
                    notification_type='error'
                )
                
                return True
        except Transaction.DoesNotExist:
            pass
        
        return False 