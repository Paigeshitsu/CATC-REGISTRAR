const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

/**
 * LBC Express Live Rate Scraper
 * Actually interacts with the LBC website to get real rates
 */

const CONFIG = {
    origin: 'Legazpi City',
    documentType: 'Document',
    serviceType: 'Courier',
    declaredValues: [100, 500, 1000, 2000, 3000, 5000]
};

class LBCLiveScraper {
    constructor() {
        this.browser = null;
        this.page = null;
        this.baseUrl = 'https://www.lbcexpress.com/rates';
        this.results = [];
    }

    async init() {
        console.log('🚀 Initializing LBC Live Scraper...');
        
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

        this.page = await this.browser.newPage();
        await this.page.setViewport({ width: 1280, height: 800 });
        await this.page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    }

    async close() {
        if (this.page) await this.page.close();
        if (this.browser) await this.browser.close();
    }

    async navigateToRatesPage() {
        console.log('📍 Navigating to LBC rates page...');
        await this.page.goto(this.baseUrl, {
            waitUntil: 'networkidle2',
            timeout: 60000
        });
        await this.page.waitForSelector('body', { timeout: 10000 });
        console.log('✅ Page loaded');
    }

    async analyzeForm() {
        console.log('🔍 Analyzing form structure...');
        
        const formInfo = await this.page.evaluate(() => {
            const info = {
                selects: [],
                inputs: [],
                buttons: []
            };

            // Find all select elements
            document.querySelectorAll('select').forEach((select, i) => {
                info.selects.push({
                    name: select.name || `select-${i}`,
                    id: select.id || `select-${i}`,
                    className: select.className,
                    options: Array.from(select.options).map(opt => ({
                        value: opt.value,
                        text: opt.text.trim()
                    })),
                    selected: select.value
                });
            });

            // Find all input elements
            document.querySelectorAll('input').forEach((input, i) => {
                info.inputs.push({
                    type: input.type,
                    name: input.name || `input-${i}`,
                    id: input.id || `input-${i}`,
                    className: input.className,
                    placeholder: input.placeholder,
                    value: input.value
                });
            });

            // Find all buttons
            document.querySelectorAll('button, input[type="submit"], input[type="button"]').forEach((btn, i) => {
                info.buttons.push({
                    type: btn.type,
                    text: btn.textContent?.trim() || `button-${i}`,
                    id: btn.id || `button-${i}`,
                    className: btn.className,
                    name: btn.name
                });
            });

            return info;
        });

        console.log('📋 Form Analysis:');
        console.log(`  - Selects found: ${formInfo.selects.length}`);
        console.log(`  - Inputs found: ${formInfo.inputs.length}`);
        console.log(`  - Buttons found: ${formInfo.buttons.length}`);

        // Log select options
        formInfo.selects.forEach((select, i) => {
            console.log(`\n  Select ${i + 1}: ${select.name}`);
            if (select.options.length <= 15) {
                select.options.forEach(opt => {
                    console.log(`    ${opt.value ? '✓' : ' '} ${opt.value || '(empty)'}: ${opt.text}`);
                });
            } else {
                console.log(`    (${select.options.length} options total)`);
                select.options.slice(0, 5).forEach(opt => {
                    console.log(`    ${opt.value ? '✓' : ' '} ${opt.value || '(empty)'}: ${opt.text}`);
                });
            }
        });

        return formInfo;
    }

    async fillFormAndCalculate(destination, declaredValue) {
        try {
            console.log(`\n📦 Calculating rate for: ${destination} (₱${declaredValue})`);

            // Navigate to rates page
            await this.navigateToRatesPage();

            // Wait a moment for page to fully load
            await new Promise(resolve => setTimeout(resolve, 2000));

            // Fill the form using JavaScript
            const result = await this.page.evaluate(async (params) => {
                const { origin, destination, declaredValue } = params;
                
                // Helper function to select option by text
                const selectByText = (selector, text) => {
                    const select = document.querySelector(selector);
                    if (!select) return false;
                    for (let option of select.options) {
                        if (option.text.toLowerCase().includes(text.toLowerCase())) {
                            select.value = option.value;
                            select.dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                        }
                    }
                    return false;
                };

                // Helper function to type in input
                const typeInInput = (selector, text) => {
                    const input = document.querySelector(selector);
                    if (!input) return false;
                    input.value = text;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                };

                // Try to find and fill transaction type (Within Philippines)
                const transactionSelectors = [
                    'select[name="transaction_type"]',
                    'select[name*="transaction"]',
                    '#transaction_type',
                    'select:first-of-type'
                ];

                for (const selector of transactionSelectors) {
                    if (selectByText(selector, 'Within')) {
                        console.log(`Selected transaction type: Within Philippines`);
                        break;
                    }
                }

                // Wait for next field to appear
                await new Promise(resolve => setTimeout(resolve, 1000));

                // Try to find and fill product category (Document)
                const productSelectors = [
                    'select[name="product_category"]',
                    'select[name*="product"]',
                    '#product_category',
                    'select:nth-of-type(2)'
                ];

                for (const selector of productSelectors) {
                    if (selectByText(selector, 'Document')) {
                        console.log(`Selected product type: Document`);
                        break;
                    }
                }

                // Wait for next field to appear
                await new Promise(resolve => setTimeout(resolve, 1000));

                // Try to find and fill origin (Legazpi City)
                const originSelectors = [
                    'input[name*="origin"]',
                    'input[name*="from"]',
                    'input[placeholder*="Origin"]',
                    'input[placeholder*="From"]',
                    '#origin',
                    '.origin-input'
                ];

                for (const selector of originSelectors) {
                    if (typeInInput(selector, origin)) {
                        console.log(`Set origin: ${origin}`);
                        break;
                    }
                }

                // Wait for next field to appear
                await new Promise(resolve => setTimeout(resolve, 1000));

                // Try to find and fill destination
                const destSelectors = [
                    'input[name*="destination"]',
                    'input[name*="to"]',
                    'input[placeholder*="Destination"]',
                    'input[placeholder*="To"]',
                    '#destination',
                    '.destination-input'
                ];

                for (const selector of destSelectors) {
                    if (typeInInput(selector, destination)) {
                        console.log(`Set destination: ${destination}`);
                        break;
                    }
                }

                // Wait for next field to appear
                await new Promise(resolve => setTimeout(resolve, 1000));

                // Try to find and fill declared value
                const valueSelectors = [
                    'input[name*="declared"]',
                    'input[name*="value"]',
                    'input[name*="amount"]',
                    'input[placeholder*="Value"]',
                    'input[placeholder*="Amount"]',
                    '#declared-value',
                    '.value-input'
                ];

                for (const selector of valueSelectors) {
                    if (typeInInput(selector, declaredValue.toString())) {
                        console.log(`Set declared value: ${declaredValue}`);
                        break;
                    }
                }

                // Wait for calculate button
                await new Promise(resolve => setTimeout(resolve, 1000));

                // Try to find and click calculate button
                const buttonSelectors = [
                    'button[type="submit"]',
                    'button:contains("Calculate")',
                    'button:contains("Get Rate")',
                    'input[type="submit"]',
                    '.calculate-btn',
                    '#calculate-btn',
                    'button.calculate'
                ];

                let buttonClicked = false;
                for (const selector of buttonSelectors) {
                    const button = document.querySelector(selector);
                    if (button) {
                        button.click();
                        buttonClicked = true;
                        console.log(`Clicked calculate button`);
                        break;
                    }
                }

                if (!buttonClicked) {
                    // Try pressing Enter on the last input
                    const inputs = document.querySelectorAll('input');
                    if (inputs.length > 0) {
                        const lastInput = inputs[inputs.length - 1];
                        lastInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
                        console.log(`Pressed Enter to calculate`);
                    }
                }

                return { success: true };
            }, { origin, destination, declaredValue });

            // Wait for results to load
            await new Promise(resolve => setTimeout(resolve, 3000));

            // Extract the rate information
            const rateData = await this.extractRate(destination, declaredValue);
            
            return rateData;

        } catch (error) {
            console.error(`Error calculating rate for ${destination}:`, error.message);
            return null;
        }
    }

    async extractRate(destination, declaredValue) {
        const rateInfo = await this.page.evaluate(() => {
            const result = {
                baseRate: null,
                totalRate: null,
                insurance: null,
                handlingFee: null,
                deliveryTime: null,
                error: null
            };

            // Get all text content from the page
            const pageText = document.body.innerText;

            // Look for price patterns
            const pricePatterns = [
                /(?:total|rate|price|fee)\s*[:\-]?\s*₱?\s*([\d,]+\.?\d*)/i,
                /₱\s*([\d,]+\.?\d*)/g,
                /(\d+)\s*\/-/,
                /php\s*([\d,]+\.?\d*)/i
            ];

            const prices = [];
            pricePatterns.forEach(pattern => {
                const matches = pageText.matchAll(pattern);
                for (const match of matches) {
                    const price = parseFloat(match[1].replace(/,/g, ''));
                    if (price > 0 && !prices.includes(price)) {
                        prices.push(price);
                    }
                }
            });

            // Look for delivery time patterns
            const deliveryPatterns = [
                /(\d+)\s*-\s*(\d+)\s*(?:business\s*)?days?/i,
                /(\d+)\s*(?:business\s*)?days?/i,
                /estimated\s*:?(\d+)\s*days?/i
            ];

            for (const pattern of deliveryPatterns) {
                const match = pageText.match(pattern);
                if (match) {
                    if (match[2]) {
                        result.deliveryTime = `${match[1]}-${match[2]} business days`;
                    } else {
                        result.deliveryTime = `${match[1]}-${parseInt(match[1]) + 2} business days`;
                    }
                    break;
                }
            }

            // If we found prices, use them
            if (prices.length > 0) {
                // Sort prices and pick relevant ones
                prices.sort((a, b) => a - b);
                
                // Assume smallest is base rate, largest is total
                result.baseRate = prices[0];
                result.totalRate = prices[prices.length - 1];
                
                // Calculate insurance and handling if we have enough prices
                if (prices.length >= 2) {
                    result.insurance = result.totalRate - result.baseRate - 50; // Assume 50 handling
                    result.handlingFee = 50;
                } else {
                    result.insurance = 0;
                    result.handlingFee = 50;
                }
            }

            // Check for error messages
            const errorPatterns = [
                /not\s*available/i,
                /no\s*rate\s*found/i,
                /invalid/i,
                /error/i
            ];

            for (const pattern of errorPatterns) {
                if (pattern.test(pageText)) {
                    result.error = 'Rate not available';
                    break;
                }
            }

            return result;
        });

        return rateInfo;
    }

    async run() {
        try {
            await this.init();
            
            // Test destinations
            const testDestinations = [
                'Manila',
                'Quezon City',
                'Cebu City',
                'Davao City',
                'Baguio'
            ];

            console.log('\n🧪 Testing with sample destinations...');
            
            for (const destination of testDestinations) {
                for (const declaredValue of [1000, 5000]) {
                    try {
                        const rate = await this.fillFormAndCalculate(destination, declaredValue);
                        
                        if (rate && rate.totalRate) {
                            console.log(`✅ ${destination} (₱${declaredValue}): ₱${rate.totalRate}`);
                            this.results.push({
                                origin: CONFIG.origin,
                                destination,
                                declaredValue,
                                baseRate: rate.baseRate,
                                insurance: rate.insurance,
                                handlingFee: rate.handlingFee,
                                total: rate.totalRate,
                                estimatedDelivery: rate.deliveryTime || 'N/A',
                                currency: 'PHP'
                            });
                        } else {
                            console.log(`❌ ${destination} (₱${declaredValue}): Rate not available`);
                        }
                    } catch (error) {
                        console.log(`❌ ${destination} (₱${declaredValue}): ${error.message}`);
                    }
                    
                    // Wait between requests
                    await new Promise(resolve => setTimeout(resolve, 2000));
                }
            }

            // Save results
            if (this.results.length > 0) {
                await this.saveResults();
            } else {
                console.log('\n⚠️ No rates could be scraped. The website structure may have changed.');
            }

        } catch (error) {
            console.error('❌ Error during scraping:', error);
        } finally {
            await this.close();
        }
    }

    async saveResults() {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `lbc-live-rates-${timestamp}.json`;
        const filepath = path.join(__dirname, filename);

        const output = {
            generatedAt: new Date().toISOString(),
            source: 'LBC Express Website (Live Scraping)',
            origin: CONFIG.origin,
            documentType: 'Courier Pouch Regular',
            currency: 'PHP',
            totalResults: this.results.length,
            rates: this.results
        };

        fs.writeFileSync(filepath, JSON.stringify(output, null, 2));
        console.log(`\n💾 Results saved to: ${filepath}`);

        // Also save as CSV
        this.saveAsCSV();
    }

    saveAsCSV() {
        const csvRows = [];
        csvRows.push('Origin,Destination,Declared Value,Base Rate,Insurance,Handling Fee,Total,Estimated Delivery,Currency');

        this.results.forEach(rate => {
            csvRows.push(`${rate.origin},"${rate.destination}",${rate.declaredValue},${rate.baseRate || 'N/A'},${rate.insurance || 'N/A'},${rate.handlingFee || 'N/A'},${rate.total},"${rate.estimatedDelivery || 'N/A'}",${rate.currency}`);
        });

        const csvContent = csvRows.join('\n');
        const csvPath = path.join(__dirname, 'lbc-live-rates.csv');
        fs.writeFileSync(csvPath, csvContent);
        console.log(`📊 CSV saved to: ${csvPath}`);
    }
}

// Main execution
async function main() {
    const scraper = new LBCLiveScraper();
    await scraper.run();
}

// Run if called directly
if (require.main === module) {
    main().catch(console.error);
}

module.exports = LBCLiveScraper;