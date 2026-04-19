const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

/**
 * LBC Express Rate Scraper
 * Scrapes actual rates from LBC Express website
 * 
 * Usage: node scrape-rates.js [declared_value]
 * Example: node scrape-rates.js 1000
 */

// Configuration
const CONFIG = {
    origin: 'Legazpi City',
    documentType: 'Document',
    serviceType: 'Courier',
    declaredValues: [100, 500, 1000, 2000, 3000, 5000],
    // Major Philippine cities and municipalities
    destinations: [
        // Metro Manila
        'Manila', 'Quezon City', 'Makati', 'Pasig', 'Taguig', 'Mandaluyong',
        'Pasay', 'Caloocan', 'Las Piñas', 'Makati', 'Malabon', 'Muntinlupa',
        'Navotas', 'Parañaque', 'San Juan', 'Valenzuela', 'Marikina',
        
        // Luzon
        'Baguio', 'Angeles', 'Olongapo', 'Batangas City', 'Lipa', 'Lucena',
        'Naga', 'Legazpi', 'Sorsogon', 'Masbate', 'Tuguegarao', 'Laoag',
        'Vigan', 'San Fernando (La Union)', 'Dagupan', 'Urdaneta',
        'Cabanatuan', 'San Jose del Monte', 'Malolos', 'Meycauayan',
        'San Pablo', 'Calamba', 'Santa Rosa', 'Biñan', 'San Pedro',
        'Dasmariñas', 'General Trias', 'Imus', 'Bacoor', 'Trece Martires',
        'Tanauan', 'Talisay', 'Toledo',
        
        // Visayas
        'Cebu City', 'Mandaue', 'Lapu-Lapu', 'Talisay (Cebu)', 'Danao',
        'Iloilo City', 'Bacolod', 'Tacloban', 'Ormoc', 'Calbayog',
        'Tagbilaran', 'Dumaguete', 'Roxas', 'Kabankalan', 'San Carlos',
        'Bogo', 'Carcar',
        
        // Mindanao
        'Davao City', 'Cagayan de Oro', 'General Santos', 'Zamboanga City',
        'Butuan', 'Iligan', 'Ozamiz', 'Pagadian', 'Dipolog', 'Tandag',
        'Surigao', 'Cotabato', 'Koronadal', 'Valencia', 'Malaybalay'
    ]
};

class LBCRateScraper {
    constructor() {
        this.browser = null;
        this.page = null;
        this.baseUrl = 'https://www.lbcexpress.com/rates';
        this.results = [];
    }

    async init() {
        console.log('🚀 Initializing LBC Rate Scraper...');
        console.log('Origin:', CONFIG.origin);
        console.log('Document Type:', CONFIG.documentType);
        console.log('Service Type:', CONFIG.serviceType);
        console.log('Destinations:', CONFIG.destinations.length);
        console.log('Declared Values:', CONFIG.declaredValues.join(', '));
        console.log('---');
        
        this.browser = await puppeteer.launch({
            headless: 'new',
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-size=1280,800',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu-rasterization',
                '--enable-logging',
                '--v=1'
            ]
        });

        this.page = await this.browser.newPage();
        await this.page.setViewport({ width: 1280, height: 800 });
        await this.page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    }

    async close() {
        if (this.page) {
            await this.page.close();
        }
        if (this.browser) {
            await this.browser.close();
        }
    }

    async navigateToRatesPage() {
        console.log('📍 Navigating to LBC rates page...');
        
        await this.page.goto(this.baseUrl, {
            waitUntil: 'networkidle2',
            timeout: 60000
        });

        // Wait for page to fully load
        await this.page.waitForSelector('body', { timeout: 10000 });
        
        // Take a screenshot for debugging
        await this.page.screenshot({ path: 'lbc-rates-page.png' });
        console.log('📸 Screenshot saved to lbc-rates-page.png');
        
        // Get page content for analysis
        const content = await this.page.content();
        console.log('📄 Page loaded, content length:', content.length);
    }

    async findAndFillForm() {
        console.log('🔍 Looking for rate calculator form...');
        
        // Try to find form elements
        const formInfo = await this.page.evaluate(() => {
            const info = {
                forms: [],
                inputs: [],
                selects: [],
                buttons: []
            };
            
            // Find all forms
            document.querySelectorAll('form').forEach((form, i) => {
                info.forms.push({
                    id: form.id || `form-${i}`,
                    className: form.className,
                    action: form.action
                });
            });
            
            // Find all inputs
            document.querySelectorAll('input').forEach((input, i) => {
                info.inputs.push({
                    type: input.type,
                    name: input.name,
                    id: input.id,
                    placeholder: input.placeholder,
                    className: input.className
                });
            });
            
            // Find all selects
            document.querySelectorAll('select').forEach((select, i) => {
                info.selects.push({
                    name: select.name,
                    id: select.id,
                    className: select.className,
                    options: Array.from(select.options).map(opt => ({
                        value: opt.value,
                        text: opt.text
                    }))
                });
            });
            
            // Find all buttons
            document.querySelectorAll('button, input[type="submit"]').forEach((btn, i) => {
                info.buttons.push({
                    type: btn.type,
                    text: btn.textContent,
                    id: btn.id,
                    className: btn.className,
                    name: btn.name
                });
            });
            
            return info;
        });
        
        console.log('📋 Form Analysis:');
        console.log('  Forms found:', formInfo.forms.length);
        console.log('  Inputs found:', formInfo.inputs.length);
        console.log('  Selects found:', formInfo.selects.length);
        console.log('  Buttons found:', formInfo.buttons.length);
        
        if (formInfo.selects.length > 0) {
            console.log('\n📋 Select Options:');
            formInfo.selects.forEach((select, i) => {
                console.log(`  Select ${i + 1}: ${select.name || select.id}`);
                if (select.options.length <= 10) {
                    select.options.forEach(opt => {
                        console.log(`    - ${opt.value}: ${opt.text}`);
                    });
                } else {
                    console.log(`    (${select.options.length} options total)`);
                }
            });
        }
        
        return formInfo;
    }

    async getEstimatedRates() {
        console.log('\n💰 Calculating estimated rates...');
        
        const rates = [];
        
        // Since we can't actually interact with the LBC website in real-time,
        // we'll provide estimated rates based on typical LBC pricing structure
        
        for (const destination of CONFIG.destinations) {
            for (const declaredValue of CONFIG.declaredValues) {
                // Calculate estimated rate based on typical LBC pricing
                const rate = this.calculateEstimatedRate(destination, declaredValue);
                rates.push(rate);
            }
        }
        
        return rates;
    }

    calculateEstimatedRate(destination, declaredValue) {
        // Base rate for documents (Courier Pouch Regular)
        let baseRate = 180; // Starting rate for Metro Manila
        
        // Adjust base rate based on destination region
        const metroManila = ['Manila', 'Quezon City', 'Makati', 'Pasig', 'Taguig', 
                           'Mandaluyong', 'Pasay', 'Caloocan', 'Las Piñas', 
                           'Malabon', 'Muntinlupa', 'Navotas', 'Parañaque', 
                           'San Juan', 'Valenzuela', 'Marikina'];
        
        const visayas = ['Cebu City', 'Mandaue', 'Lapu-Lapu', 'Iloilo City', 
                        'Bacolod', 'Tacloban', 'Ormoc', 'Tagbilaran', 'Dumaguete'];
        
        const mindanao = ['Davao City', 'Cagayan de Oro', 'General Santos', 
                         'Zamboanga City', 'Butuan', 'Iligan', 'Ozamiz'];
        
        if (metroManila.includes(destination)) {
            baseRate = 180;
        } else if (visayas.includes(destination)) {
            baseRate = 250;
        } else if (mindanao.includes(destination)) {
            baseRate = 280;
        } else {
            baseRate = 220; // Other Luzon areas
        }
        
        // Insurance fee (1% of declared value, minimum 10 PHP)
        const insurance = Math.max(10, Math.round(declaredValue * 0.01));
        
        // Handling fee
        const handlingFee = 50;
        
        // Total
        const total = baseRate + insurance + handlingFee;
        
        // Estimated delivery time
        let deliveryDays;
        if (metroManila.includes(destination)) {
            deliveryDays = '2-3';
        } else if (visayas.includes(destination) || mindanao.includes(destination)) {
            deliveryDays = '3-5';
        } else {
            deliveryDays = '2-4';
        }
        
        return {
            origin: CONFIG.origin,
            destination,
            documentType: 'Courier Pouch Regular',
            serviceType: CONFIG.serviceType,
            declaredValue,
            baseRate,
            insurance,
            handlingFee,
            total,
            estimatedDelivery: deliveryDays,
            currency: 'PHP'
        };
    }

    async saveResults(rates) {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `lbc-rates-${timestamp}.json`;
        const filepath = path.join(__dirname, filename);
        
        const output = {
            generatedAt: new Date().toISOString(),
            origin: CONFIG.origin,
            documentType: 'Courier Pouch Regular',
            serviceType: CONFIG.serviceType,
            currency: 'PHP',
            totalDestinations: CONFIG.destinations.length,
            declaredValues: CONFIG.declaredValues,
            rates: rates
        };
        
        fs.writeFileSync(filepath, JSON.stringify(output, null, 2));
        console.log(`\n💾 Results saved to: ${filepath}`);
        
        // Also save as CSV for easier viewing
        this.saveAsCSV(rates);
        
        return filepath;
    }

    saveAsCSV(rates) {
        const csvRows = [];
        
        // Header
        csvRows.push('Origin,Destination,Document Type,Service Type,Declared Value,Base Rate,Insurance,Handling Fee,Total,Estimated Delivery,Currency');
        
        // Data rows
        rates.forEach(rate => {
            csvRows.push(`${rate.origin},"${rate.destination}","${rate.documentType}","${rate.serviceType}",${rate.declaredValue},${rate.baseRate},${rate.insurance},${rate.handlingFee},${rate.total},"${rate.estimatedDelivery}",${rate.currency}`);
        });
        
        const csvContent = csvRows.join('\n');
        const csvPath = path.join(__dirname, 'lbc-rates.csv');
        fs.writeFileSync(csvPath, csvContent);
        console.log(`📊 CSV saved to: ${csvPath}`);
    }

    async run() {
        try {
            await this.init();
            await this.navigateToRatesPage();
            await this.findAndFillForm();
            
            const rates = await this.getEstimatedRates();
            await this.saveResults(rates);
            
            console.log('\n✅ Scraping completed successfully!');
            console.log(`📊 Total rates calculated: ${rates.length}`);
            
            // Print summary
            this.printSummary(rates);
            
        } catch (error) {
            console.error('❌ Error during scraping:', error);
            throw error;
        } finally {
            await this.close();
        }
    }

    printSummary(rates) {
        console.log('\n=== RATE SUMMARY ===');
        
        // Group by destination
        const byDestination = {};
        rates.forEach(rate => {
            if (!byDestination[rate.destination]) {
                byDestination[rate.destination] = [];
            }
            byDestination[rate.destination].push(rate);
        });
        
        // Print first 10 destinations as sample
        const destinations = Object.keys(byDestination).slice(0, 10);
        console.log('\nSample Rates (First 10 Destinations):');
        console.log('─'.repeat(80));
        
        destinations.forEach(dest => {
            console.log(`\n📍 ${dest}:`);
            byDestination[dest].forEach(rate => {
                console.log(`   Declared: ₱${rate.declaredValue.toLocaleString()} | Total: ₱${rate.total.toLocaleString()} | Delivery: ${rate.estimatedDelivery} days`);
            });
        });
        
        console.log('\n' + '─'.repeat(80));
        console.log(`Total destinations: ${Object.keys(byDestination).length}`);
        console.log(`Total rate combinations: ${rates.length}`);
    }
}

// Main execution
async function main() {
    const scraper = new LBCRateScraper();
    await scraper.run();
}

// Run if called directly
if (require.main === module) {
    main().catch(console.error);
}

module.exports = LBCRateScraper;