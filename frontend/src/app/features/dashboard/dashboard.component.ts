import { Component, signal } from '@angular/core';
import { StatusComponent } from '../../core/status/status.component';

@Component({
  selector: 'app-dashboard',
  imports: [StatusComponent],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss']
})
export class DashboardComponent {
  protected readonly title = signal('MyFullstackTemplate Dashboard');
}
