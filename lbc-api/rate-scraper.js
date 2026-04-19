const puppeteer = require('puppeteer');

/**
 * LBC Express Rate Calculator Scraper
 * Scrapes shipping rates from LBC Express website
 */
class LBCRateScraper {
    constructor() {
        this.browser = null;
        this.page = null;
        this.baseUrl = 'https://www.lbcexpress.com/rates';
    }

    async init() {
        console.log('Initializing LBC Rate Scraper...');
        
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

    async scrapeRates() {
        try {
            console.log('Navigating to LBC rates page...');
            await this.page.goto(this.baseUrl, {
                waitUntil: 'networkidle2',
                timeout: 30000
            });

            // Wait for the page to load
            await this.page.waitForSelector('body', { timeout: 10000 });

            // Check if we're on the correct page
            const pageTitle = await this.page.title();
            console.log('Page title:', pageTitle);

            // Try to find the rate calculator form
            const formSelectors = [
                'form',
                '.rate-calculator',
                '.calculator-form',
                '#rate-calculator',
                '.shipping-form'
            ];

            let formFound = false;
            for (const selector of formSelectors) {
                try {
                    const form = await this.page.$(selector);
                    if (form) {
                        formFound = true;
                        console.log(`Found form with selector: ${selector}`);
                        break;
                    }
                } catch (e) {
                    continue;
                }
            }

            if (!formFound) {
                console.log('No form found, trying to find input fields directly...');
                return await this.scrapeAlternative();
            }

            return await this.scrapeWithForm();

        } catch (error) {
            console.error('Error during scraping:', error);
            throw error;
        }
    }

    async scrapeWithForm() {
        // Set origin to Legazpi City
        await this.setOrigin('Legazpi City');
        
        // Set document type to Courier Pouch Regular
        await this.setDocumentType('Courier Pouch Regular');
        
        // Get all destination cities
        const destinations = await this.getAllDestinations();
        
        const rates = [];
        
        for (const destination of destinations) {
            try {
                console.log(`Scraping rate for: ${destination}`);
                
                // Set destination
                await this.setDestination(destination);
                
                // Calculate rates for different declared values
                const rateData = await this.calculateRatesForDestination(destination);
                
                rates.push({
                    destination: destination,
                    rates: rateData
                });
                
                // Small delay to avoid overwhelming the server
                await new Promise(resolve => setTimeout(resolve, 1000));
                
            } catch (error) {
                console.error(`Error scraping rate for ${destination}:`, error.message);
                continue;
            }
        }

        return rates;
    }

    async scrapeAlternative() {
        // Alternative scraping method if form-based approach fails
        console.log('Using alternative scraping method...');
        
        // Try to extract any rate tables or data from the page
        const rateData = await this.page.evaluate(() => {
            const results = [];
            
            // Look for tables that might contain rates
            const tables = document.querySelectorAll('table');
            tables.forEach((table, index) => {
                const rows = table.querySelectorAll('tr');
                const tableData = [];
                
                rows.forEach(row => {
                    const cells = row.querySelectorAll('td, th');
                    const rowData = Array.from(cells).map(cell => cell.textContent.trim());
                    if (rowData.length > 0) {
                        tableData.push(rowData);
                    }
                });
                
                if (tableData.length > 0) {
                    results.push({
                        tableIndex: index,
                        data: tableData
                    });
                }
            });

            // Look for any divs that might contain rate information
            const rateDivs = document.querySelectorAll('[class*="rate"], [class*="price"], [class*="fee"]');
            rateDivs.forEach(div => {
                const text = div.textContent.trim();
                if (text && text.length > 10) {
                    results.push({
                        type: 'div',
                        content: text
                    });
                }
            });

            return results;
        });

        return rateData;
    }

    async setOrigin(city) {
        // Try to find and set the origin city
        const originSelectors = [
            'input[name*="origin"]',
            'input[name*="from"]',
            'select[name*="origin"]',
            'select[name*="from"]',
            '#origin',
            '#from-city',
            '.origin-input',
            '.from-input'
        ];

        for (const selector of originSelectors) {
            try {
                const element = await this.page.$(selector);
                if (element) {
                    await element.click({ clickCount: 3 });
                    await element.type(city, { delay: 100 });
                    console.log(`Set origin to: ${city}`);
                    return true;
                }
            } catch (e) {
                continue;
            }
        }
        
        throw new Error('Origin input not found');
    }

    async setDocumentType(type) {
        // Try to find and set the document type
        const typeSelectors = [
            'select[name*="type"]',
            'select[name*="document"]',
            'input[name*="type"]',
            '#document-type',
            '.document-type-select'
        ];

        for (const selector of typeSelectors) {
            try {
                const element = await this.page.$(selector);
                if (element) {
                    // Try to select the option
                    await element.select('Courier Pouch Regular');
                    console.log(`Set document type to: ${type}`);
                    return true;
                }
            } catch (e) {
                continue;
            }
        }
        
        throw new Error('Document type selector not found');
    }

    async setDestination(city) {
        // Try to find and set the destination city
        const destinationSelectors = [
            'input[name*="destination"]',
            'input[name*="to"]',
            'select[name*="destination"]',
            'select[name*="to"]',
            '#destination',
            '#to-city',
            '.destination-input',
            '.to-input'
        ];

        for (const selector of destinationSelectors) {
            try {
                const element = await this.page.$(selector);
                if (element) {
                    await element.click({ clickCount: 3 });
                    await element.type(city, { delay: 100 });
                    console.log(`Set destination to: ${city}`);
                    return true;
                }
            } catch (e) {
                continue;
            }
        }
        
        throw new Error('Destination input not found');
    }

    async getAllDestinations() {
        // Try to find a list of destination cities
        const destinationSelectors = [
            'select[name*="destination"] option',
            'select[name*="to"] option',
            '#destination option',
            '.destination-list option'
        ];

        for (const selector of destinationSelectors) {
            try {
                const cities = await this.page.$$eval(selector, options => 
                    options.map(option => option.textContent.trim()).filter(city => city.length > 0)
                );
                
                if (cities.length > 0) {
                    console.log(`Found ${cities.length} destination cities`);
                    return cities.slice(0, 50); // Limit to first 50 cities to avoid overwhelming
                }
            } catch (e) {
                continue;
            }
        }

        // If no dropdown found, try to extract cities from the page
        const cities = await this.page.evaluate(() => {
            const text = document.body.textContent;
            // Look for common Philippine city patterns
            const cityPatterns = [
                /(?:from|to|destination)\s*[:\-]?\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)/gi,
                /([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s*(?:to|from|destination)/gi
            ];
            
            const cities = [];
            cityPatterns.forEach(pattern => {
                let match;
                while ((match = pattern.exec(text)) !== null) {
                    cities.push(match[1].trim());
                }
            });
            
            return [...new Set(cities)].slice(0, 20); // Remove duplicates and limit
        });

        return cities;
    }

    async calculateRatesForDestination(destination) {
        // Try to trigger rate calculation
        const calculateSelectors = [
            'button[type="submit"]',
            'button:has-text("Calculate")',
            'button:has-text("Get Rate")',
            '.calculate-btn',
            '#calculate-rate'
        ];

        for (const selector of calculateSelectors) {
            try {
                const button = await this.page.$(selector);
                if (button) {
                    await button.click();
                    await new Promise(resolve => setTimeout(resolve, 2000)); // Wait for calculation
                    break;
                }
            } catch (e) {
                continue;
            }
        }

        // Extract rate information
        const rateInfo = await this.page.evaluate(() => {
            const results = {
                baseRate: '',
                totalRate: '',
                breakdown: {},
                estimatedDelivery: ''
            };

            // Look for rate displays
            const rateElements = document.querySelectorAll('[class*="rate"], [class*="price"], [class*="amount"]');
            rateElements.forEach(el => {
                const text = el.textContent.trim();
                if (text.match(/\d+[\.,]?\d*/)) {
                    if (!results.baseRate) results.baseRate = text;
                    else if (!results.totalRate) results.totalRate = text;
                }
            });

            // Look for delivery time
            const deliveryElements = document.querySelectorAll('[class*="delivery"], [class*="time"], [class*="eta"]');
            deliveryElements.forEach(el => {
                const text = el.textContent.trim();
                if (text.match(/\d+\s*(?:day|hour|week)/i)) {
                    results.estimatedDelivery = text;
                }
            });

            return results;
        });

        return rateInfo;
    }

    async close() {
        if (this.browser) {
            await this.browser.close();
        }
    }
}

// Main execution
async function main() {
    const scraper = new LBCRateScraper();
    
    try {
        await scraper.init();
        const rates = await scraper.scrapeRates();
        
        console.log('\n=== LBC RATES SCRAPING RESULTS ===');
        console.log(JSON.stringify(rates, null, 2));
        
    } catch (error) {
        console.error('Scraping failed:', error);
    } finally {
        await scraper.close();
    }
}

// Run if called directly
if (require.main === module) {
    main();
}

module.exports = LBCRateScraper;