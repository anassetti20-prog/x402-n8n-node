import type { IExecuteFunctions, INodeExecutionData, INodeType, INodeTypeDescription } from 'n8n-workflow';
import { NodeApiError } from 'n8n-workflow';

/**
 * x402 Service Definitions — matching the x402 Multi-Service API registry
 * Each service has its parameters, price, and description.
 */
interface ServiceParam {
	name: string;
	displayName: string;
	type: 'string' | 'number' | 'boolean';
	default: string | number | boolean;
	required: boolean;
	description: string;
}

interface ServiceConfig {
	name: string;
	price: number;
	description: string;
	params: ServiceParam[];
}

const X402_SERVICES: Record<string, ServiceConfig> = {
	'halal-check': {
		name: 'Halal Screening',
		price: 0.01,
		description: 'Check if a cryptocurrency is Sharia-compliant',
		params: [
			{ name: 'symbol', displayName: 'Symbol', type: 'string', default: 'BTC', required: true, description: 'Cryptocurrency symbol (e.g., BTC, ETH)' },
		],
	},
	web_search: {
		name: 'Web Search',
		price: 0.01,
		description: 'Search the web for information',
		params: [
			{ name: 'query', displayName: 'Query', type: 'string', default: '', required: true, description: 'Search query' },
		],
	},
	analyze_code: {
		name: 'Code Analysis',
		price: 0.01,
		description: 'Analyze source code for bugs, security issues, and optimization',
		params: [
			{ name: 'code', displayName: 'Code', type: 'string', default: '', required: true, description: 'Source code to analyze' },
			{ name: 'language', displayName: 'Language', type: 'string', default: '', required: false, description: 'Programming language (e.g., python, javascript)' },
		],
	},
	process_data: {
		name: 'Data Processing',
		price: 0.01,
		description: 'Transform, filter, validate, or convert structured data',
		params: [
			{ name: 'data', displayName: 'Data', type: 'string', default: '', required: true, description: 'Input data to process' },
			{ name: 'operation', displayName: 'Operation', type: 'string', default: 'json-validate', required: false, description: 'Operation to perform' },
		],
	},
	translate_text: {
		name: 'Translation',
		price: 0.01,
		description: 'Translate text between languages',
		params: [
			{ name: 'text', displayName: 'Text', type: 'string', default: '', required: true, description: 'Text to translate' },
			{ name: 'target_lang', displayName: 'Target Language', type: 'string', default: 'en', required: true, description: 'Target language code (e.g., en, de, fr, es, ar)' },
			{ name: 'source_lang', displayName: 'Source Language', type: 'string', default: '', required: false, description: 'Source language code (leave empty for auto-detect)' },
		],
	},
	generate_text: {
		name: 'Text Generation',
		price: 0.02,
		description: 'Generate AI text in various styles and formats',
		params: [
			{ name: 'prompt', displayName: 'Prompt', type: 'string', default: '', required: true, description: 'Text prompt for AI generation' },
			{ name: 'style', displayName: 'Style', type: 'string', default: '', required: false, description: 'Writing style (e.g., formal, creative, technical)' },
			{ name: 'max_tokens', displayName: 'Max Tokens', type: 'number', default: 500, required: false, description: 'Maximum tokens to generate' },
		],
	},
	uuid_generate: {
		name: 'UUID Generator',
		price: 0.01,
		description: 'Generate UUIDs (v4)',
		params: [
			{ name: 'count', displayName: 'Count', type: 'number', default: 1, required: false, description: 'Number of UUIDs to generate (1-100)' },
		],
	},
	hash_generate: {
		name: 'Hash Generator',
		price: 0.01,
		description: 'Generate cryptographic hashes',
		params: [
			{ name: 'text', displayName: 'Text', type: 'string', default: '', required: true, description: 'Input text to hash' },
			{ name: 'algorithm', displayName: 'Algorithm', type: 'string', default: 'sha256', required: false, description: 'Hash algorithm (md5, sha1, sha256, sha512)' },
		],
	},
	base64_process: {
		name: 'Base64 Process',
		price: 0.01,
		description: 'Encode or decode Base64',
		params: [
			{ name: 'text', displayName: 'Text', type: 'string', default: '', required: true, description: 'Input text to encode/decode' },
			{ name: 'mode', displayName: 'Mode', type: 'string', default: 'encode', required: true, description: 'Operation: encode or decode' },
		],
	},
	password_generate: {
		name: 'Password Generator',
		price: 0.01,
		description: 'Generate secure random passwords',
		params: [
			{ name: 'length', displayName: 'Length', type: 'number', default: 16, required: false, description: 'Password length (8-128)' },
		],
	},
	text_stats: {
		name: 'Text Statistics',
		price: 0.01,
		description: 'Get detailed statistics about text',
		params: [
			{ name: 'text', displayName: 'Text', type: 'string', default: '', required: true, description: 'Input text to analyze' },
		],
	},
	json_process: {
		name: 'JSON Processor',
		price: 0.01,
		description: 'Validate, format, or transform JSON',
		params: [
			{ name: 'json', displayName: 'JSON', type: 'string', default: '', required: true, description: 'JSON string to process' },
			{ name: 'operation', displayName: 'Operation', type: 'string', default: 'validate', required: false, description: 'Operation (validate, format, minify)' },
		],
	},
	qrcode_generate: {
		name: 'QR Code Generator',
		price: 0.01,
		description: 'Generate QR codes from text or URLs',
		params: [
			{ name: 'text', displayName: 'Text/URL', type: 'string', default: '', required: true, description: 'Text or URL to encode in QR code' },
		],
	},
	sentiment_analyze: {
		name: 'Sentiment Analysis',
		price: 0.01,
		description: 'Analyze sentiment of text',
		params: [
			{ name: 'text', displayName: 'Text', type: 'string', default: '', required: true, description: 'Text to analyze for sentiment' },
		],
	},
};

// Build service list for n8n dropdown
const serviceOptions = Object.entries(X402_SERVICES).map(([id, svc]) => ({
	name: `$${svc.price.toFixed(2)} ${svc.name}`,
	value: id,
	description: svc.description,
}));

export class X402Node implements INodeType {
	description: INodeTypeDescription = {
		displayName: 'x402 API',
		name: 'x402Api',
		icon: {
			light: 'file:logoLight.svg',
			dark: 'file:logoDark.svg',
		},
		group: ['transform'],
		version: 1,
		subtitle: '={{$parameter["service"] + " ($" + $parameter["price"] + ")"}}',
		description:
			'Use x402 API services — pay-per-use AI tools via USDC micropayments on Base chain',
		defaults: {
			name: 'x402 API',
		},
		inputs: ['main'],
		outputs: ['main'],
		credentials: [
			{
				name: 'x402Api',
				required: true,
			},
		],
		properties: [
			// ── Service Selection ──
			{
				displayName: 'Service',
				name: 'service',
				type: 'options',
				options: serviceOptions,
				default: 'web_search',
				required: true,
				description: 'Select the x402 API service to use',
			},

			// ── Price display (hidden, used in subtitle) ──
			{
				displayName: 'Price',
				name: 'price',
				type: 'hidden',
				default: 0.01,
			},

			// ── Service Parameters ──
			// Halal Check
			{
				displayName: 'Symbol',
				name: 'symbol',
				type: 'string',
				default: 'BTC',
				displayOptions: { show: { service: ['halal-check'] } },
				required: true,
				description: 'Cryptocurrency symbol (e.g., BTC, ETH, SOL)',
			},
			// Web Search
			{
				displayName: 'Query',
				name: 'query',
				type: 'string',
				default: '',
				displayOptions: { show: { service: ['web_search'] } },
				required: true,
				description: 'Search query',
			},
			// Code Analysis
			{
				displayName: 'Code',
				name: 'code',
				type: 'string',
				typeOptions: { rows: 8 },
				default: '',
				displayOptions: { show: { service: ['analyze_code'] } },
				required: true,
				description: 'Source code to analyze',
			},
			{
				displayName: 'Language',
				name: 'language',
				type: 'string',
				default: '',
				displayOptions: { show: { service: ['analyze_code'] } },
				required: false,
				description: 'Programming language (e.g., python, javascript)',
			},
			// Data Processing
			{
				displayName: 'Data',
				name: 'data',
				type: 'string',
				default: '',
				displayOptions: { show: { service: ['process_data'] } },
				required: true,
				description: 'Input data to process',
			},
			// Translation
			{
				displayName: 'Text',
				name: 'translation_text',
				type: 'string',
				default: '',
				displayOptions: { show: { service: ['translate_text'] } },
				required: true,
				description: 'Text to translate',
			},
			{
				displayName: 'Target Language',
				name: 'target_lang',
				type: 'string',
				default: 'en',
				displayOptions: { show: { service: ['translate_text'] } },
				required: true,
				description: 'Target language code (e.g., en, de, fr, es, ar)',
			},
			{
				displayName: 'Source Language',
				name: 'source_lang',
				type: 'string',
				default: '',
				displayOptions: { show: { service: ['translate_text'] } },
				required: false,
				description: 'Source language code (leave empty for auto-detect)',
			},
			// Text Generation
			{
				displayName: 'Prompt',
				name: 'prompt',
				type: 'string',
				typeOptions: { rows: 4 },
				default: '',
				displayOptions: { show: { service: ['generate_text'] } },
				required: true,
				description: 'Text prompt for AI generation',
			},
			// UUID Generator
			{
				displayName: 'Count',
				name: 'uuid_count',
				type: 'number',
				default: 1,
				displayOptions: { show: { service: ['uuid_generate'] } },
				description: 'Number of UUIDs to generate (1-100)',
			},
			// Hash Generator
			{
				displayName: 'Text',
				name: 'hash_text',
				type: 'string',
				default: '',
				displayOptions: { show: { service: ['hash_generate'] } },
				required: true,
				description: 'Input text to hash',
			},
			{
				displayName: 'Algorithm',
				name: 'hash_algorithm',
				type: 'options',
				options: [
					{ name: 'MD5', value: 'md5' },
					{ name: 'SHA-1', value: 'sha1' },
					{ name: 'SHA-256', value: 'sha256' },
					{ name: 'SHA-512', value: 'sha512' },
				],
				default: 'sha256',
				displayOptions: { show: { service: ['hash_generate'] } },
				description: 'Hash algorithm',
			},
			// Base64
			{
				displayName: 'Text',
				name: 'base64_text',
				type: 'string',
				default: '',
				displayOptions: { show: { service: ['base64_process'] } },
				required: true,
				description: 'Input text to encode/decode',
			},
			{
				displayName: 'Mode',
				name: 'base64_mode',
				type: 'options',
				options: [
					{ name: 'Encode', value: 'encode' },
					{ name: 'Decode', value: 'decode' },
				],
				default: 'encode',
				displayOptions: { show: { service: ['base64_process'] } },
				description: 'Encode or decode',
			},
			// Password Generator
			{
				displayName: 'Length',
				name: 'password_length',
				type: 'number',
				default: 16,
				displayOptions: { show: { service: ['password_generate'] } },
				description: 'Password length (8-128)',
			},
			// Text Stats
			{
				displayName: 'Text',
				name: 'stats_text',
				type: 'string',
				default: '',
				displayOptions: { show: { service: ['text_stats'] } },
				required: true,
				description: 'Input text to analyze',
			},
			// QR Code
			{
				displayName: 'Text/URL',
				name: 'qrcode_text',
				type: 'string',
				default: '',
				displayOptions: { show: { service: ['qrcode_generate'] } },
				required: true,
				description: 'Text or URL to encode in QR code',
			},
			// Sentiment Analysis
			{
				displayName: 'Text',
				name: 'sentiment_text',
				type: 'string',
				default: '',
				displayOptions: { show: { service: ['sentiment_analyze'] } },
				required: true,
				description: 'Text to analyze for sentiment',
			},
			// JSON Processor
			{
				displayName: 'JSON',
				name: 'json_data',
				type: 'string',
				typeOptions: { rows: 6 },
				default: '',
				displayOptions: { show: { service: ['json_process'] } },
				required: true,
				description: 'JSON string to process',
			},
			{
				displayName: 'Operation',
				name: 'json_operation',
				type: 'options',
				options: [
					{ name: 'Validate', value: 'validate' },
					{ name: 'Format', value: 'format' },
					{ name: 'Minify', value: 'minify' },
				],
				default: 'validate',
				displayOptions: { show: { service: ['json_process'] } },
				description: 'JSON processing operation',
			},

			// ── Payment Mode ──
			{
				displayName: 'Payment Mode',
				name: 'paymentMode',
				type: 'options',
				options: [
					{
						name: 'Internal Key (Server-side — No Payment)',
						value: 'internal',
						description: 'Use internal API key (no USDC payment required — local server only)',
					},
					{
						name: 'Manual (Provide TX Hash)',
						value: 'manual',
						description: 'Manually provide USDC transaction hash as proof of payment',
					},
				],
				default: 'manual',
				description: 'How to handle x402 network payments',
			},

			// ── Manual Transaction Hash ──
			{
				displayName:
					'⚠️ To use this service, send {{$parameter["price"]}} USDC on Base (chain 8453) to 0xeB262928D55A92f2EAac946807CeC4d80E9EdD6B, then enter the transaction hash below.',
				name: 'paymentNotice',
				type: 'notice',
				displayOptions: { show: { paymentMode: ['manual'] } },
				default: '',
			},
			{
				displayName: 'Transaction Hash (Proof of Payment)',
				name: 'txHash',
				type: 'string',
				default: '',
				displayOptions: { show: { paymentMode: ['manual'] } },
				description:
					'USDC transaction hash on Base chain as payment proof. Leave empty to receive payment instructions in output.',
			},
		],
	};

	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const items = this.getInputData();
		const returnData: INodeExecutionData[] = [];

		const credentials = await this.getCredentials('x402Api');
		if (!credentials) {
			throw new NodeApiError(this.getNode(), {
				message: 'x402 API credentials are required',
			});
		}

		const baseUrl = (credentials.baseUrl as string).replace(/\/+$/, '');
		const internalKey = credentials.internalKey as string;

		for (const [index] of items.entries()) {
			const serviceId = this.getNodeParameter('service', index, '') as string;
			const paymentMode = this.getNodeParameter('paymentMode', index, 'manual') as string;
			const serviceData = X402_SERVICES[serviceId];

			if (!serviceData) {
				throw new NodeApiError(this.getNode(), {
					message: `Unknown service: ${serviceId}`,
				});
			}

			// ── Collect parameters ──
			const params: Record<string, unknown> = {};
			for (const param of serviceData.params) {
				try {
					const value = this.getNodeParameter(param.name, index, param.default);
					if (value !== '' && value !== undefined && value !== null) {
						params[param.name] = value;
					}
				} catch {
					// Parameter not found, skip
				}
			}

			const isHalalCheck = serviceId === 'halal-check';

			// Build URL
			let url: string;
			if (isHalalCheck) {
				const symbol = String(params['symbol'] || 'BTC');
				url = `${baseUrl}/halal-check?symbol=${encodeURIComponent(symbol)}`;
			} else {
				url = `${baseUrl}/v1/${serviceId}`;
			}

			// ── Build headers with payment info ──
			const headers: Record<string, string> = {
				'Content-Type': 'application/json',
				'User-Agent': 'n8n-x402-node/1.0.0',
			};

			if (paymentMode === 'internal' && internalKey) {
				headers['X-Internal-Key'] = internalKey;
			} else if (paymentMode === 'manual') {
				const txHash = this.getNodeParameter('txHash', index, '') as string;
				if (txHash) {
					headers['X-402-Proof'] = txHash;
				}
			}

			try {
				const response = await this.helpers.httpRequest({
					method: isHalalCheck ? 'GET' : 'POST',
					url,
					headers,
					...(isHalalCheck ? {} : { body: params }),
					skipSslCertificateValidation: true,
					returnFullResponse: true,
				});

				returnData.push({
					json: {
						service: serviceId,
						service_name: serviceData.name,
						price_paid: serviceData.price,
						statusCode: response.statusCode,
						...response.body,
					},
				});
			} catch (error: any) {
				// Handle x402 Payment Required (HTTP 402)
				if (error.response?.status === 402) {
					const paymentInfo = error.response.data || {};
					returnData.push({
						json: {
							error: 'Payment Required',
							service: serviceId,
							service_name: serviceData.name,
							price_usdc: serviceData.price,
							instruction: `Send ${serviceData.price} USDC on Base chain (8453) to the recipient address below, then retry with the transaction hash`,
							payment: {
								price_usdc: serviceData.price,
								chain: 'Base (8453)',
								chain_id: 8453,
								recipient: '0xeB262928D55A92f2EAac946807CeC4d80E9EdD6B',
								token: 'USDC',
								token_contract: '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
							},
							response: paymentInfo,
						},
					});
				} else {
					const errorMessage = error.message;
					let errorDetail = '';
					if (error.response?.data) {
						errorDetail = typeof error.response.data === 'string' ? error.response.data : JSON.stringify(error.response.data);
					}
					const n8nError = new Error(`x402 API error: ${errorMessage}`);
					if (errorDetail) {
						(n8nError as any).description = errorDetail;
					}
					throw new NodeApiError(this.getNode(), n8nError as any);
				}
			}
		}

		return [returnData];
	}
}
