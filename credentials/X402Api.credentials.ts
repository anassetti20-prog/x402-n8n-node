import type {
	IAuthenticateGeneric,
	ICredentialTestRequest,
	ICredentialType,
	INodeProperties,
} from 'n8n-workflow';

export class X402Api implements ICredentialType {
	name = 'x402Api';
	displayName = 'x402 API';
	documentationUrl = 'https://trades-could-directory-permalink.trycloudflare.com';
	properties: INodeProperties[] = [
		{
			displayName: 'API Base URL',
			name: 'baseUrl',
			type: 'string',
			default: 'https://trades-could-directory-permalink.trycloudflare.com',
			description: 'Base URL of the x402 API server',
		},
		{
			displayName: 'Internal API Key (optional)',
			name: 'internalKey',
			type: 'string',
			typeOptions: {
				password: true,
			},
			default: '',
			description: 'Optional internal API key for bypassing x402 payment (server-side use only)',
		},
		{
			displayName: 'Web3 Private Key (optional)',
			name: 'privateKey',
			type: 'string',
			typeOptions: {
				password: true,
			},
			default: '',
			description: 'Optional Ethereum private key for signing x402 payments. Required if no internal key is provided.',
		},
		{
			displayName: 'USDC Contract Address (Base)',
			name: 'usdcContract',
			type: 'string',
			default: '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
			description: 'USDC contract address on Base',
		},
		{
			displayName: 'Base RPC URL',
			name: 'rpcUrl',
			type: 'string',
			default: 'https://mainnet.base.org',
			description: 'Base chain RPC endpoint',
		},
	];

	authenticate: IAuthenticateGeneric = {
		type: 'generic',
		properties: {
			headers: {},
		},
	};

	test: ICredentialTestRequest = {
		request: {
			baseURL: '={{$credentials.baseUrl}}',
			url: '/health',
			method: 'GET',
		},
	};
}
