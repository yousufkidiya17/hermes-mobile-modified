// Hermes Mobile LocalBridge - Model Proxy
// Lightweight Node.js server for LLM API proxying (OpenCode Zen API)

const http = require('http');
const https = require('https');

const PORT = 4000;
const ZEN_API = 'opencode.ai';
const ZEN_PATH = '/zen/v1/chat/completions';
const API_KEY = 'aetherix-master-7x9k2m4p';
const DEFAULT_MODEL = 'opencode/mimo-v2.5-free';

const MODELS = [
    { id: 'opencode/mimo-v2.5-free', zenId: 'mimo-v2.5-free' },
    { id: 'opencode/deepseek-v4-flash-free', zenId: 'deepseek-v4-flash-free' },
    { id: 'opencode/nemotron-3-ultra-free', zenId: 'nemotron-3-ultra-free' },
    { id: 'opencode/ling-3.0-flash-free', zenId: 'ling-3.0-flash-free' },
];

function proxyToZen(reqBody, res) {
    const data = JSON.stringify({
        ...reqBody,
        model: DEFAULT_MODEL
    });

    const options = {
        hostname: ZEN_API,
        path: ZEN_PATH,
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(data),
        }
    };

    const zenReq = https.request(options, (zenRes) => {
        res.writeHead(zenRes.statusCode, zenRes.headers);
        zenRes.pipe(res);
    });

    zenReq.on('error', (e) => {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: e.message }));
    });

    zenReq.write(data);
    zenReq.end();
}

const server = http.createServer((req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

    if (req.method === 'OPTIONS') {
        res.writeHead(204);
        res.end();
        return;
    }

    if (req.url === '/health' || req.url === '/') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
            status: 'ok',
            service: 'Hermes Mobile LocalBridge',
            models: MODELS.length
        }));
        return;
    }

    if (req.url === '/v1/models') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ data: MODELS }));
        return;
    }

    if (req.url === '/v1/chat/completions') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', () => {
            try {
                const parsed = JSON.parse(body);
                proxyToZen(parsed, res);
            } catch (e) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Invalid JSON' }));
            }
        });
        return;
    }

    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not found' }));
});

server.listen(PORT, '127.0.0.1', () => {
    console.log(`Hermes Mobile LocalBridge running on http://127.0.0.1:${PORT}`);
    console.log(`Default model: ${DEFAULT_MODEL}`);
});
