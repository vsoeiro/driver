import { Check, ChevronDown } from 'lucide-react';
import { useAccountsQuery } from '../hooks/useAppQueries';
import ProviderIcon from './ProviderIcon';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from './ui/dropdown-menu';

export default function AccountSwitcher({
    selectedAccountId = '',
    onSelectAccount,
    accountLabel,
    placeholderLabel,
}) {
    const { data: accounts = [] } = useAccountsQuery();
    const selectedAccount = accounts.find((account) => account.id === selectedAccountId) || null;

    return (
        <div className="relative flex min-w-0 flex-1 items-center gap-2">
            <span className="hidden text-xs font-medium text-muted-foreground sm:inline">{accountLabel}</span>
            <DropdownMenu>
                <DropdownMenuTrigger
                    className="input-shell inline-flex h-9 w-full min-w-0 items-center justify-between gap-2 px-2.5 text-sm disabled:opacity-50 sm:min-w-[220px] sm:max-w-[340px]"
                    disabled={accounts.length === 0}
                >
                    <span className="inline-flex min-w-0 items-center gap-2">
                        {selectedAccount ? (
                            <>
                                <ProviderIcon provider={selectedAccount.provider} className="h-4 w-4 shrink-0" />
                                <span className="truncate">{selectedAccount.email}</span>
                            </>
                        ) : (
                            <span className="text-muted-foreground">{placeholderLabel}</span>
                        )}
                    </span>
                    <ChevronDown size={16} className="shrink-0 text-muted-foreground" />
                </DropdownMenuTrigger>
                <DropdownMenuContent
                    className="layer-popover max-h-72 w-[min(340px,calc(100vw-2rem))] overflow-auto rounded-sm border-border/90 bg-card p-1"
                    align="start"
                >
                    {accounts.map((account) => (
                        <DropdownMenuItem
                            key={account.id}
                            className="flex w-full items-center justify-between gap-3 rounded-sm px-3 py-2 text-left"
                            onClick={() => onSelectAccount(account.id)}
                        >
                            <span className="inline-flex min-w-0 items-center gap-2">
                                <ProviderIcon provider={account.provider} className="h-4 w-4 shrink-0" />
                                <span className="truncate text-sm">{account.email}</span>
                            </span>
                            {account.id === selectedAccountId && <Check size={14} className="text-primary" />}
                        </DropdownMenuItem>
                    ))}
                </DropdownMenuContent>
            </DropdownMenu>
        </div>
    );
}
