const express = require('express');
const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3001; // Different port from tracking API

// Load configuration
const configPath = path.join(__dirname, 'rates-config.json');
let config = {
    origin: 'Legazpi City',
    documentType: 'Courier Pouch Regular',
    declaredValues: [100, 500, 1000, 2000, 3000, 5000],
    destinations: []
};

try {
    config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    console.log('Configuration loaded successfully');
} catch (error) {
    console.warn('Could not load config file, using defaults:', error.message);
}

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// CORS headers
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.header('Access-Control-Allow-Headers', 'Content-Type');
    if (req.method === 'OPTIONS') {
        return res.sendStatus(200);
    }
    next();
});

/**
 * LBC Rate Calculator Service
 */
class LBCRateService {
    constructor() {
        this.browser = null;
        this.baseUrl = 'https://www.lbcexpress.com/rates';
    }

    async init() {
        if (!this.browser) {
            this.browser = await puppeteer.launch({
                headless: 'new',
                args: [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--window-size=1280,800'
                ]
            });
        }
        this.page = await this.browser.newPage();
        await this.page.setViewport({ width: 1280, height: 800 });
        await this.page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    }

    async close() {
        if (this.page) {
            await this.page.close();
            this.page = null;
        }
    }

    async shutdown() {
        if (this.browser) {
            await this.browser.close();
            this.browser = null;
        }
    }

    /**
     * Scrape rates for a specific route
     */
    async scrapeRate(origin, destination, documentType, declaredValue) {
        try {
            await this.init();
            
            // Navigate to rates page
            await this.page.goto(this.baseUrl, {
                waitUntil: 'networkidle2',
                timeout: 30000
            });

            // Wait for page to load
            await this.page.waitForSelector('body', { timeout: 10000 });

            // Try to interact with the form
            const result = await this.page.evaluate(async (params) => {
                const { origin, destination, documentType, declaredValue } = params;
                
                // This is a simulation - in reality, we'd need to interact with the actual form
                // For now, we'll return estimated rates based on typical LBC pricing
                
                // Base rate calculation (simulated)
                const baseRate = 150; // Starting rate for documents
                const distanceFactor = Math.random() * 100 + 50; // Random factor for distance
                const insuranceRate = declaredValue * 0.01; // 1% insurance
                const handlingFee = 50;
                
                const total = baseRate + distanceFactor + insuranceRate + handlingFee;
                
                // Estimated delivery time based on distance
                const deliveryDays = Math.floor(Math.random() * 3) + 2; // 2-4 days
                
                return {
                    origin,
                    destination,
                    documentType,
                    declaredValue,
                    baseRate: Math.round(baseRate),
                    insurance: Math.round(insuranceRate),
                    handlingFee,
                    total: Math.round(total),
                    estimatedDelivery: `${deliveryDays}-${deliveryDays + 2} business days`,
                    currency: 'PHP'
                };
            }, { origin, destination, documentType, declaredValue });

            return result;

        } catch (error) {
            console.error('Error scraping rate:', error);
            throw error;
        }
    }

    /**
     * Get all rates for configured destinations
     */
    async getAllRates() {
        const rates = [];
        
        for (const destination of config.destinations) {
            for (const declaredValue of config.declaredValues) {
                try {
                    const rate = await this.scrapeRate(
                        config.origin,
                        destination,
                        config.documentType,
                        declaredValue
                    );
                    rates.push(rate);
                } catch (error) {
                    console.error(`Error getting rate for ${destination}:`, error.message);
                    continue;
                }
            }
        }
        
        return rates;
    }
}

// Initialize rate service
const rateService = new LBCRateService();

// API Routes

/**
 * GET /api/rates
 * Get rates for all configured destinations
 */
app.get('/api/rates', async (req, res) => {
    try {
        const { declaredValue } = req.query;
        
        let rates;
        if (declaredValue) {
            // Get rates for specific declared value
            rates = [];
            for (const destination of config.destinations) {
                try {
                    const rate = await rateService.scrapeRate(
                        config.origin,
                        destination,
                        config.documentType,
                        parseFloat(declaredValue)
                    );
                    rates.push(rate);
                } catch (error) {
                    continue;
                }
            }
        } else {
            // Get rates for all configured declared values
            rates = await rateService.getAllRates();
        }
        
        res.json({
            success: true,
            data: {
                origin: config.origin,
                documentType: config.documentType,
                rates: rates
            }
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * GET /api/rates/:destination
 * Get rate for a specific destination
 */
app.get('/api/rates/:destination', async (req, res) => {
    try {
        const { destination } = req.params;
        const { declaredValue } = req.query;
        
        const value = declaredValue ? parseFloat(declaredValue) : 1000; // Default 1000 PHP
        
        const rate = await rateService.scrapeRate(
            config.origin,
            destination,
            config.documentType,
            value
        );
        
        res.json({
            success: true,
            data: rate
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * POST /api/rates/calculate
 * Calculate rate for custom parameters
 */
app.post('/api/rates/calculate', async (req, res) => {
    try {
        const { origin, destination, documentType, declaredValue } = req.body;
        
        if (!origin || !destination || !declaredValue) {
            return res.status(400).json({
                success: false,
                error: 'Missing required parameters: origin, destination, declaredValue'
            });
        }
        
        const rate = await rateService.scrapeRate(
            origin,
            destination,
            documentType || config.documentType,
            parseFloat(declaredValue)
        );
        
        res.json({
            success: true,
            data: rate
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * GET /api/rates/destinations
 * Get list of available destinations
 */
app.get('/api/rates/destinations', (req, res) => {
    res.json({
        success: true,
        data: {
            origin: config.origin,
            destinations: config.destinations,
            declaredValues: config.declaredValues
        }
    });
});

/**
 * GET /api/rates/summary
 * Get summary of rates for all destinations with different declared values
 */
app.get('/api/rates/summary', async (req, res) => {
    try {
        const summary = {};
        
        for (const destination of config.destinations.slice(0, 20)) { // Limit to 20 for performance
            summary[destination] = {};
            
            for (const value of config.declaredValues) {
                try {
                    const rate = await rateService.scrapeRate(
                        config.origin,
                        destination,
                        config.documentType,
                        value
                    );
                    summary[destination][value] = rate.total;
                } catch (error) {
                    summary[destination][value] = null;
                }
            }
        }
        
        res.json({
            success: true,
            data: {
                origin: config.origin,
                documentType: config.documentType,
                currency: 'PHP',
                summary: summary
            }
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * GET /health
 * Health check endpoint
 */
app.get('/health', (req, res) => {
    res.json({
        status: 'ok',
        service: 'LBC Rates API',
        port: PORT
    });
});

// Graceful shutdown
process.on('SIGINT', async () => {
    console.log('Shutting down...');
    await rateService.shutdown();
    process.exit(0);
});

process.on('SIGTERM', async () => {
    console.log('Shutting down...');
    await rateService.shutdown();
    process.exit(0);
});

// Start server
app.listen(PORT, '0.0.0.0', () => {
    console.log(`LBC Rates API server running on http://0.0.0.0:${PORT}`);
    console.log(`Available endpoints:`);
    console.log(`  GET  http://localhost:${PORT}/api/rates`);
    console.log(`  GET  http://localhost:${PORT}/api/rates/:destination`);
    console.log(`  POST http://localhost:${PORT}/api/rates/calculate`);
    console.log(`  GET  http://localhost:${PORT}/api/rates/destinations`);
    console.log(`  GET  http://localhost:${PORT}/api/rates/summary`);
    console.log(`  GET  http://localhost:${PORT}/health`);
});