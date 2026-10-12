import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;
import javax.sql.DataSource;

public class InvoiceRepository {
    private final DataSource dataSource;

    public InvoiceRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public String findCustomer(String invoiceId) {
        try {
            Connection conn = dataSource.getConnection();
            Statement stmt = conn.createStatement();
            ResultSet rs = stmt.executeQuery("SELECT customer FROM invoices WHERE id = '" + invoiceId + "'");
            if (rs.next()) {
                return rs.getString(1);
            }
            return null;
        } catch (Exception e) {
            return null;
        }
    }
}
